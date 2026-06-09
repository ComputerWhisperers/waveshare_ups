"""Tests for independent Raspberry Pi GPIO relay control."""

from types import SimpleNamespace

import pytest

from conftest import load_module

relay_module = load_module("relay")


class FakeChip:
    """Return configured GPIO chip information."""

    def __init__(self, label: str) -> None:
        self._label = label

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def get_info(self):
        return SimpleNamespace(label=self._label)


class FakeRequest:
    """Record output values written by the relay driver."""

    def __init__(self, initial) -> None:
        self.values = [initial]
        self.released = False

    def set_value(self, _line: int, value) -> None:
        self.values.append(value)

    def release(self) -> None:
        self.released = True


class FakeGpiod:
    """Minimal official gpiod v2 API used by the driver."""

    class line:
        class Direction:
            OUTPUT = "output"

        class Value:
            ACTIVE = 1
            INACTIVE = 0

    def __init__(self, labels: dict[str, str]) -> None:
        self.labels = labels
        self.last_request = None

    def is_gpiochip_device(self, device: str) -> bool:
        return device in self.labels

    def Chip(self, device: str):
        return FakeChip(self.labels[device])

    def LineSettings(self, *, direction, output_value):
        return SimpleNamespace(direction=direction, output_value=output_value)

    def request_lines(self, _device: str, *, consumer: str, config: dict):
        assert consumer == "waveshare-ups-utility-relay"
        settings = next(iter(config.values()))
        self.last_request = FakeRequest(settings.output_value)
        return self.last_request


def test_discovers_pi4_or_pi5_pinctrl_chip() -> None:
    fake = FakeGpiod(
        {
            "/dev/gpiochip0": "other-controller",
            "/dev/gpiochip4": "pinctrl-rp1",
        }
    )
    assert (
        relay_module.find_pinctrl_gpiochip(
            fake,
            ("/dev/gpiochip0", "/dev/gpiochip4"),
        )
        == "/dev/gpiochip4"
    )


def test_active_low_relay_defaults_connected_and_disconnects_low() -> None:
    fake = FakeGpiod({"/dev/gpiochip4": "pinctrl-rp1"})
    relay = relay_module.UtilityRelay(
        17,
        True,
        gpiod_module=fake,
        device_paths=("/dev/gpiochip4",),
    )

    relay.open()
    assert relay.connected is True
    assert fake.last_request.values == [1]

    relay.disconnect_utility()
    assert relay.connected is False
    assert fake.last_request.values[-1] == 0

    relay.close()
    assert fake.last_request.values[-1] == 1
    assert fake.last_request.released is True


def test_active_high_relay_disconnects_high() -> None:
    fake = FakeGpiod({"/dev/gpiochip0": "pinctrl-bcm2711"})
    relay = relay_module.UtilityRelay(
        17,
        False,
        gpiod_module=fake,
        device_paths=("/dev/gpiochip0",),
    )
    relay.open()
    relay.disconnect_utility()
    assert fake.last_request.values == [0, 1]


def test_i2c_gpio_lines_are_rejected() -> None:
    fake = FakeGpiod({"/dev/gpiochip4": "pinctrl-rp1"})
    with pytest.raises(relay_module.RelayError):
        relay_module.UtilityRelay(
            2,
            True,
            gpiod_module=fake,
            device_paths=("/dev/gpiochip4",),
        )
