from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

import comtypes
from pycaw.constants import CLSID_CPolicyConfigClient, DEVICE_STATE, EDataFlow, ERole
from pycaw.pycaw import AudioUtilities

try:
    from pycaw.api.policyconfig import IPolicyConfig
except ImportError as exc:  # pragma: no cover - import path depends on pycaw version
    raise RuntimeError(
        "pycaw does not expose IPolicyConfig. Install a recent pycaw release."
    ) from exc

try:  # pragma: no cover - older Windows fallback
    from pycaw.api.policyconfig import IPolicyConfigVista
except ImportError:  # pragma: no cover - optional on newer systems
    IPolicyConfigVista = None


CAPTURE_ROLES: tuple[ERole, ...] = (
    ERole.eConsole,
    ERole.eMultimedia,
    ERole.eCommunications,
)


class DeviceManagerError(RuntimeError):
    """Raised when Windows audio device management fails."""


class VirtualCableNotFoundError(DeviceManagerError):
    """Raised when VB-Cable is not installed or not available."""


@dataclass(frozen=True)
class RecordingDevice:
    id: str
    name: str
    state: str


def _normalize_name(device_name: str) -> str:
    return device_name.strip().lower()


def _to_recording_device(audio_device) -> RecordingDevice:
    return RecordingDevice(
        id=audio_device.id,
        name=audio_device.FriendlyName or "Unknown recording device",
        state=getattr(audio_device.state, "name", str(audio_device.state)),
    )


def _get_policy_config():
    try:
        return comtypes.CoCreateInstance(
            CLSID_CPolicyConfigClient,
            IPolicyConfig,
            comtypes.CLSCTX_ALL,
        )
    except (OSError, comtypes.COMError):
        if IPolicyConfigVista is None:
            raise

        return comtypes.CoCreateInstance(
            CLSID_CPolicyConfigClient,
            IPolicyConfigVista,
            comtypes.CLSCTX_ALL,
        )


def _set_default_for_roles(device_id: str, roles: Iterable[ERole]) -> None:
    try:
        policy_config = _get_policy_config()
        for role in roles:
            result = policy_config.SetDefaultEndpoint(device_id, role.value)
            if result != 0:
                raise DeviceManagerError(
                    f"Failed to set default microphone for role {role.name}: HRESULT {result:#x}"
                )
    except Exception as exc:  # pragma: no cover - depends on Windows audio stack
        if isinstance(exc, DeviceManagerError):
            raise
        raise DeviceManagerError("Unable to change the default recording device.") from exc


def get_recording_devices(include_inactive: bool = False) -> List[RecordingDevice]:
    state = DEVICE_STATE.MASK_ALL.value if include_inactive else DEVICE_STATE.ACTIVE.value
    devices = AudioUtilities.GetAllDevices(EDataFlow.eCapture.value, state)
    return [_to_recording_device(device) for device in devices]


def get_default_recording_device(role: ERole = ERole.eMultimedia) -> RecordingDevice:
    try:
        enumerator = AudioUtilities.GetDeviceEnumerator()
        device = enumerator.GetDefaultAudioEndpoint(EDataFlow.eCapture.value, role.value)
        return _to_recording_device(AudioUtilities.CreateDevice(device))
    except Exception as exc:  # pragma: no cover - depends on Windows audio stack
        raise DeviceManagerError("Unable to read the default recording device.") from exc


def snapshot_default_recording_devices() -> Dict[str, str]:
    snapshot: Dict[str, str] = {}
    for role in CAPTURE_ROLES:
        snapshot[role.name] = get_default_recording_device(role).id
    return snapshot


def restore_default_recording_devices(snapshot: Dict[str, str]) -> None:
    ordered_roles = []
    for role in CAPTURE_ROLES:
        device_id = snapshot.get(role.name)
        if device_id:
            ordered_roles.append((role, device_id))

    try:
        policy_config = _get_policy_config()
        for role, device_id in ordered_roles:
            result = policy_config.SetDefaultEndpoint(device_id, role.value)
            if result != 0:
                raise DeviceManagerError(
                    f"Failed to restore microphone for role {role.name}: HRESULT {result:#x}"
                )
    except Exception as exc:  # pragma: no cover - depends on Windows audio stack
        if isinstance(exc, DeviceManagerError):
            raise
        raise DeviceManagerError("Unable to restore the previous microphone.") from exc


def set_default_recording_device(device_id: str) -> None:
    _set_default_for_roles(device_id, CAPTURE_ROLES)


def find_virtual_cable(name_hint: str = "CABLE Output") -> RecordingDevice:
    normalized_hint = _normalize_name(name_hint)
    for device in get_recording_devices(include_inactive=False):
        if normalized_hint in _normalize_name(device.name):
            return device

    raise VirtualCableNotFoundError(
        "VB-Cable recording device was not found. Install VB-Audio Virtual Cable and make sure it is enabled."
    )
