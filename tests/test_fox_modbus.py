"""Regression tests for pymodbus keyword-only / device_id API compatibility.

These use fake synchronous Modbus clients whose signatures mirror the real
pymodbus releases, so no inverter or network connection is required:

* ``LegacyKwargsClient``  - pymodbus 3.0 - 3.7 (positional ``slave``, ``**kwargs``)
* ``LegacySlaveClient``   - pymodbus 3.8 / 3.9 (keyword-only ``slave``)
* ``ModernClient``        - pymodbus 3.10+    (keyword-only ``device_id``)

The fake signatures are themselves the regression assertion: the shipped bug
passed the device identifier positionally, which raises TypeError against the
keyword-only signatures.
"""

import asyncio
from functools import partial
import threading

from pymodbus.exceptions import ModbusException, ModbusIOException
import pytest

from custom_components.foxess_em.const import CONNECTION_TYPE, FOX_MODBUS_TCP
from custom_components.foxess_em.fox import fox_modbus
from custom_components.foxess_em.fox.fox_modbus import FoxModbus

_SLAVE = 247


class Response:
    """Stand-in for a pymodbus response."""

    def __init__(self, registers=None, error=False):
        self.registers = registers if registers is not None else [1]
        self._error = error

    def isError(self):  # noqa: N802 - pymodbus API name
        """Match the pymodbus response API."""
        return self._error


class RecordingClient:
    """Base fake sync client recording every call and the thread it ran on."""

    def __init__(self, result=None):
        self.calls = []
        self.threads = []
        self.result = result if result is not None else Response()

    def _record(self, name, args, kwargs):
        self.calls.append((name, args, kwargs))
        self.threads.append(threading.get_ident())
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def connect(self):
        """Connect."""
        return self._record("connect", (), {})

    def close(self):
        """Close."""
        return self._record("close", (), {})


class ModernClient(RecordingClient):
    """pymodbus >= 3.10: keyword-only count / device_id."""

    def read_input_registers(
        self, address, *, count=1, device_id=1, no_response_expected=False
    ):
        """Read input registers."""
        return self._record(
            "read_input_registers", (address,), {"count": count, "device_id": device_id}
        )

    def write_register(
        self, address, value, *, device_id=1, no_response_expected=False
    ):
        """Write a single register."""
        return self._record(
            "write_register", (address, value), {"device_id": device_id}
        )

    def write_registers(
        self, address, values, *, device_id=1, no_response_expected=False
    ):
        """Write multiple registers."""
        return self._record(
            "write_registers", (address, values), {"device_id": device_id}
        )


class LegacySlaveClient(RecordingClient):
    """pymodbus 3.8 / 3.9: keyword-only count / slave."""

    def read_input_registers(
        self, address, *, count=1, slave=1, no_response_expected=False
    ):
        """Read input registers."""
        return self._record(
            "read_input_registers", (address,), {"count": count, "slave": slave}
        )

    def write_register(self, address, value, *, slave=1, no_response_expected=False):
        """Write a single register."""
        return self._record("write_register", (address, value), {"slave": slave})

    def write_registers(self, address, values, *, slave=1, no_response_expected=False):
        """Write multiple registers."""
        return self._record("write_registers", (address, values), {"slave": slave})


class LegacyKwargsClient(RecordingClient):
    """pymodbus 3.0 - 3.7: positional-or-keyword slave behind a **kwargs sink.

    The ``**kwargs`` sink is why hard-coding ``device_id`` would be unsafe: it
    would be swallowed silently and the write would go to the default device.
    """

    def read_input_registers(self, address, count=1, slave=0, **kwargs):
        """Read input registers."""
        return self._record(
            "read_input_registers",
            (address,),
            {"count": count, "slave": slave, "extra": kwargs},
        )

    def write_register(self, address, value, slave=0, **kwargs):
        """Write a single register."""
        return self._record(
            "write_register", (address, value), {"slave": slave, "extra": kwargs}
        )

    def write_registers(self, address, values, slave=0, **kwargs):
        """Write multiple registers."""
        return self._record(
            "write_registers", (address, values), {"slave": slave, "extra": kwargs}
        )


class UnsupportedClient(RecordingClient):
    """A client exposing neither 'device_id' nor 'slave'."""

    def read_input_registers(self, address, *, count=1, unit=1):
        """Read input registers."""
        return self._record("read_input_registers", (address,), {"count": count})

    def write_register(self, address, value, *, unit=1):
        """Write a single register."""
        return self._record("write_register", (address, value), {})

    def write_registers(self, address, values, *, unit=1):
        """Write multiple registers."""
        return self._record("write_registers", (address, values), {})


class FakeHass:
    """Minimal stand-in for the bits of HomeAssistant FoxModbus uses."""

    def __init__(self):
        self.executor_jobs = []

    def async_create_task(self, coro):
        """Swallow the background connect() so tests do no I/O."""
        coro.close()

    async def async_add_executor_job(self, target, *args):
        """Run in a real executor thread, like Home Assistant does."""
        self.executor_jobs.append((target, args))
        return await asyncio.get_running_loop().run_in_executor(None, target, *args)


def build(client):
    """Build a FoxModbus wired to a fake client and fake hass."""
    hass = FakeHass()
    modbus = FoxModbus(
        hass,
        {CONNECTION_TYPE: FOX_MODBUS_TCP, "host": "127.0.0.1", "port": 502},
    )
    modbus._client = client
    return modbus, hass


def run(coro):
    """Drive a coroutine without needing an asyncio pytest plugin."""
    return asyncio.run(coro)


def identifier(client_class):
    """The identifier keyword the given fake client expects."""
    return "device_id" if client_class is ModernClient else "slave"


ALL_CLIENTS = [ModernClient, LegacySlaveClient, LegacyKwargsClient]


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------


@pytest.mark.parametrize("client_class", ALL_CLIENTS)
def test_read_registers_passes_count_and_identifier_by_keyword(client_class):
    """Reads pass count by keyword and the configured device identifier."""
    client = client_class(Response(registers=[11, 22]))
    modbus, _ = build(client)

    assert run(modbus.read_registers(40002, 2, _SLAVE)) == [11, 22]

    name, args, kwargs = client.calls[0]
    assert name == "read_input_registers"
    assert args == (40002,), "address must be the only positional argument"
    assert kwargs["count"] == 2
    assert kwargs[identifier(client_class)] == _SLAVE


def test_read_registers_does_not_leak_device_id_into_legacy_kwargs():
    """A 3.0-3.7 client must receive 'slave', not a swallowed 'device_id'."""
    client = LegacyKwargsClient(Response(registers=[3]))
    modbus, _ = build(client)

    run(modbus.read_registers(40002, 1, _SLAVE))

    _, _, kwargs = client.calls[0]
    assert kwargs["slave"] == _SLAVE
    assert kwargs["extra"] == {}, "no unexpected kwargs may be swallowed"


def test_read_registers_converts_to_signed_16_bit():
    """Existing signed conversion behaviour is preserved."""
    client = ModernClient(Response(registers=[0, 100, 32767, 32768, 65535]))
    modbus, _ = build(client)

    assert run(modbus.read_registers(31000, 5, _SLAVE)) == [0, 100, 32767, -32768, -1]


def test_read_registers_raises_on_error_response():
    """An error response is surfaced, not silently returned."""
    client = ModernClient(Response(error=True))
    modbus, _ = build(client)

    with pytest.raises(ModbusIOException):
        run(modbus.read_registers(40002, 1, _SLAVE))


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("client_class", ALL_CLIENTS)
def test_single_value_uses_write_register(client_class):
    """One value uses write_register with address, value and the identifier."""
    client = client_class()
    modbus, _ = build(client)

    assert run(modbus.write_registers(41011, [42], _SLAVE)) is True

    name, args, kwargs = client.calls[0]
    assert name == "write_register"
    assert args == (41011, 42)
    assert kwargs[identifier(client_class)] == _SLAVE


@pytest.mark.parametrize("client_class", ALL_CLIENTS)
def test_multiple_values_use_write_registers(client_class):
    """Multiple values use write_registers with integer-normalised values."""
    client = client_class()
    modbus, _ = build(client)

    assert run(modbus.write_registers(41001, [1, 30.0, 330.9, 0, 0, 0], _SLAVE)) is True

    name, args, kwargs = client.calls[0]
    assert name == "write_registers"
    assert args == (41001, [1, 30, 330, 0, 0, 0])
    assert all(isinstance(value, int) for value in args[1])
    assert kwargs[identifier(client_class)] == _SLAVE


def test_successful_write_resets_error_counter():
    """A success returns True and clears the accumulated write errors."""
    client = ModernClient()
    modbus, _ = build(client)
    modbus._write_errors = 3

    assert run(modbus.write_registers(41011, [42], _SLAVE)) is True
    assert modbus._write_errors == 0


def test_error_response_retries_then_gives_up(monkeypatch):
    """A genuine Modbus error response retries _WRITE_ATTEMPTS times."""
    monkeypatch.setattr(fox_modbus, "_WRITE_ERROR_SLEEP", 0)
    client = ModernClient(Response(error=True))
    modbus, _ = build(client)

    # Falsy rather than False: the existing _handle_write_error drops the
    # recursive return value. Behaviour preserved deliberately, not asserted.
    assert not run(modbus.write_registers(41011, [42], _SLAVE))
    assert len(client.calls) == fox_modbus._WRITE_ATTEMPTS
    assert modbus._write_errors == 0


def test_modbus_exception_retries_then_gives_up(monkeypatch):
    """A raised ModbusException follows the same retry path."""
    monkeypatch.setattr(fox_modbus, "_WRITE_ERROR_SLEEP", 0)
    client = ModernClient(ModbusException("boom"))
    modbus, _ = build(client)

    assert not run(modbus.write_registers(41011, [42], _SLAVE))
    assert len(client.calls) == fox_modbus._WRITE_ATTEMPTS


def test_type_error_is_not_retried(monkeypatch):
    """API misuse fails loudly instead of being retried as a transient fault."""
    monkeypatch.setattr(fox_modbus, "_WRITE_ERROR_SLEEP", 0)
    client = ModernClient(TypeError("positional argument"))
    modbus, _ = build(client)

    with pytest.raises(TypeError):
        run(modbus.write_registers(41011, [42], _SLAVE))
    assert len(client.calls) == 1


def test_unsupported_client_fails_clearly():
    """Neither identifier supported: fail rather than address device 0."""
    modbus, _ = build(UnsupportedClient())

    with pytest.raises(TypeError, match="Unsupported pymodbus version"):
        run(modbus.write_registers(41011, [42], _SLAVE))

    with pytest.raises(TypeError, match="Unsupported pymodbus version"):
        run(modbus.read_registers(40002, 1, _SLAVE))


# --------------------------------------------------------------------------
# Executor plumbing
# --------------------------------------------------------------------------


def test_kwargs_are_bound_into_a_partial_for_the_executor():
    """Keyword arguments reach the executor as a bound callable, unevaluated."""
    client = ModernClient()
    modbus, hass = build(client)

    run(modbus.write_registers(41011, [42], _SLAVE))

    target, args = hass.executor_jobs[0]
    assert isinstance(target, partial)
    assert args == (), "kwargs must be bound, not passed alongside"
    assert target.func == client.write_register
    assert target.keywords == {"device_id": _SLAVE}


def test_call_runs_off_the_event_loop_thread():
    """Blocking Modbus I/O must not execute on the event loop."""
    client = ModernClient()
    modbus, _ = build(client)

    run(modbus.write_registers(41011, [42], _SLAVE))

    assert client.threads[0] != threading.get_ident()


def test_calls_without_kwargs_still_use_the_plain_executor_path():
    """connect() and close() take no kwargs and must keep working."""
    client = ModernClient()
    modbus, hass = build(client)

    run(modbus.connect())
    run(modbus.close())

    assert [name for name, _, _ in client.calls] == ["connect", "close"]
    assert [target for target, _ in hass.executor_jobs] == [
        client.connect,
        client.close,
    ]
    assert all(args == () for _, args in hass.executor_jobs)
