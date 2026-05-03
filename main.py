from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sys

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QFont, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from audio_player import (
    AudioPlayer,
    AudioPlayerError,
    find_default_speaker_index,
    find_output_device_index,
)
from config_manager import SoundEntry, load_config, save_config
from device_manager import (
    DeviceManagerError,
    find_virtual_cable,
    get_default_recording_device,
    restore_default_recording_devices,
    set_default_recording_device,
    snapshot_default_recording_devices,
)


SUPPORTED_FILE_FILTER = "Audio files (*.mp3 *.wav *.ogg *.flac *.aac *.m4a);;All files (*.*)"
DEFAULT_CARD_COLUMNS = 3
MAX_CARD_COLUMNS = 4
CARD_MIN_WIDTH = 220

DARK_QSS = """
QWidget {
    background-color: #0f172a;
    color: #e5e7eb;
    font-family: Segoe UI, Arial, sans-serif;
    font-size: 14px;
}

QFrame#Container,
QFrame#Toolbar,
QFrame#StatusFrame {
    background-color: #111827;
    border: 1px solid #1f2937;
    border-radius: 18px;
}

QFrame#TransparentFrame {
    background-color: transparent;
    border: none;
}

QFrame#SoundCard {
    background-color: #111827;
    border: 1px solid #374151;
    border-radius: 16px;
}

QFrame#SoundCard[active="true"] {
    background-color: #1f2937;
    border: 2px solid #2563eb;
}

QLabel {
    background-color: transparent;
    border: none;
}

QLabel#MutedLabel {
    color: #9ca3af;
}

QPushButton {
    background-color: #2563eb;
    border: 1px solid #2563eb;
    border-radius: 8px;
    color: #f9fafb;
    font-weight: 600;
    min-height: 34px;
    padding: 6px 12px;
}

QPushButton:hover {
    background-color: #1d4ed8;
    border-color: #1d4ed8;
}

QPushButton:disabled {
    background-color: #374151;
    border-color: #374151;
    color: #9ca3af;
}

QPushButton#DangerButton {
    background-color: #9b1c1c;
    border-color: #9b1c1c;
}

QPushButton#DangerButton:hover {
    background-color: #7f1d1d;
    border-color: #7f1d1d;
}

QPushButton#OutlineButton {
    background-color: transparent;
    border: 1px solid #4b5563;
    color: #d1d5db;
}

QPushButton#OutlineButton:hover {
    background-color: #1f2937;
    border-color: #6b7280;
}

QScrollArea {
    background-color: #111827;
    border: 1px solid #1f2937;
    border-radius: 16px;
}

QScrollArea > QWidget > QWidget {
    background-color: #111827;
}

QScrollBar:vertical {
    background: #111827;
    border: none;
    width: 12px;
    margin: 10px 0 10px 0;
}

QScrollBar::handle:vertical {
    background: #374151;
    border-radius: 6px;
    min-height: 24px;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QSlider::groove:horizontal {
    background: #374151;
    border-radius: 4px;
    height: 8px;
}

QSlider::handle:horizontal {
    background: #2563eb;
    border: 2px solid #93c5fd;
    border-radius: 8px;
    margin: -5px 0;
    width: 16px;
}
"""


class SoundCard(QFrame):
    def __init__(
        self,
        sound: SoundEntry,
        on_play: Callable[[str], None],
        on_stop: Callable[[str], None],
        on_edit: Callable[[str], None],
        on_remove: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.sound = sound
        self._on_play = on_play
        self._on_stop = on_stop
        self._on_edit = on_edit
        self._on_remove = on_remove

        self.setObjectName("SoundCard")
        self.setProperty("active", False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.name_label = QLabel(sound.display_name)
        self.name_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)

        self.file_label = QLabel(Path(sound.file_path).name)
        self.file_label.setObjectName("MutedLabel")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        controls_layout = QGridLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setHorizontalSpacing(12)
        controls_layout.setVerticalSpacing(8)
        layout.addLayout(controls_layout)

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(lambda: self._on_play(self.sound.id))
        controls_layout.addWidget(self.play_button, 0, 0)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("DangerButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(lambda: self._on_stop(self.sound.id))
        controls_layout.addWidget(self.stop_button, 0, 1)

        self.edit_button = QPushButton("Edit")
        self.edit_button.setObjectName("OutlineButton")
        self.edit_button.clicked.connect(lambda: self._on_edit(self.sound.id))
        controls_layout.addWidget(self.edit_button, 1, 0)

        self.remove_button = QPushButton("Remove")
        self.remove_button.setObjectName("OutlineButton")
        self.remove_button.clicked.connect(lambda: self._on_remove(self.sound.id))
        controls_layout.addWidget(self.remove_button, 1, 1)

    def update_sound(self, sound: SoundEntry) -> None:
        self.sound = sound
        self.name_label.setText(sound.display_name)
        self.file_label.setText(Path(sound.file_path).name)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.play_button.setEnabled(not active)
        self.stop_button.setEnabled(active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class _PlaybackBridge(QObject):
    playback_finished = Signal(bool)
    playback_error = Signal(object)


class DiscordAudioSoundboardApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Discord Audio Soundboard")
        self.resize(900, 600)
        self.setMinimumSize(760, 500)

        self.player = AudioPlayer()
        self.app_config = load_config()
        self.sound_cards: dict[str, SoundCard] = {}
        self.previous_microphone_snapshot: dict[str, str] | None = None
        self.active_sound_id: str | None = None
        self.after_stop_action: Callable[[], None] | None = None
        self.is_closing = False
        self._sound_grid_columns = DEFAULT_CARD_COLUMNS
        self._resize_pending = False
        self._last_window_width = 0

        current_mic_name = self._safe_current_mic_name()

        self.status_text = "Ready"
        self.microphone_text = f"Current microphone: {current_mic_name}"
        self.playback_device_text = "Virtual playback device: not resolved yet"
        self.volume_value = float(self.app_config.global_volume)

        self.playback_bridge = _PlaybackBridge(self)
        self.playback_bridge.playback_finished.connect(self._on_playback_finished)
        self.playback_bridge.playback_error.connect(self._on_playback_error)

        self._build_ui()
        self._update_volume_label()
        self._render_sound_cards()

    def _build_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(24, 24, 24, 24)

        container = QFrame()
        container.setObjectName("Container")
        root_layout.addWidget(container)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(24, 24, 24, 24)
        container_layout.setSpacing(12)

        title = QLabel("Discord Audio Soundboard")
        title.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        container_layout.addWidget(title)

        description = QLabel(
            "Save your sounds locally, label them with text or emoji, and play them through VB-Cable."
        )
        description.setWordWrap(True)
        container_layout.addWidget(description)

        toolbar = QFrame()
        toolbar.setObjectName("Toolbar")
        container_layout.addWidget(toolbar)

        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(18, 18, 18, 18)
        toolbar_layout.setSpacing(18)

        add_sound_button = QPushButton("Add Sound")
        add_sound_button.setFixedWidth(150)
        add_sound_button.clicked.connect(self.add_sound)
        toolbar_layout.addWidget(add_sound_button)

        volume_frame = QFrame()
        volume_frame.setObjectName("TransparentFrame")
        toolbar_layout.addWidget(volume_frame, stretch=1)

        volume_layout = QGridLayout(volume_frame)
        volume_layout.setContentsMargins(0, 0, 0, 0)
        volume_layout.setHorizontalSpacing(12)
        volume_layout.setVerticalSpacing(8)

        volume_label = QLabel("Playback volume")
        volume_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        volume_layout.addWidget(volume_label, 0, 0)

        self.volume_value_label = QLabel()
        self.volume_value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        volume_layout.addWidget(self.volume_value_label, 0, 1)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(round(self.volume_value)))
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        volume_layout.addWidget(self.volume_slider, 1, 0, 1, 2)

        sounds_title = QLabel("Sounds")
        sounds_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        container_layout.addWidget(sounds_title)

        self.sounds_scroll_area = QScrollArea()
        self.sounds_scroll_area.setWidgetResizable(True)
        container_layout.addWidget(self.sounds_scroll_area, stretch=1)

        self.sounds_container = QWidget()
        self.sounds_grid = QGridLayout(self.sounds_container)
        self.sounds_grid.setContentsMargins(12, 12, 12, 12)
        self.sounds_grid.setHorizontalSpacing(10)
        self.sounds_grid.setVerticalSpacing(10)
        self.sounds_scroll_area.setWidget(self.sounds_container)

        status_frame = QFrame()
        status_frame.setObjectName("StatusFrame")
        container_layout.addWidget(status_frame)

        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(18, 16, 18, 16)
        status_layout.setSpacing(8)

        self.status_label = QLabel(self.status_text)
        self.status_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)

        self.microphone_label = QLabel(self.microphone_text)
        self.microphone_label.setWordWrap(True)
        status_layout.addWidget(self.microphone_label)

        self.playback_device_label = QLabel(self.playback_device_text)
        self.playback_device_label.setWordWrap(True)
        status_layout.addWidget(self.playback_device_label)

    def _render_sound_cards(self) -> None:
        while self.sounds_grid.count():
            item = self.sounds_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self.sound_cards.clear()
        self._configure_grid_columns()

        if not self.app_config.sounds:
            empty_label = QLabel("No sounds saved yet. Use Add Sound to build your board.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setWordWrap(True)
            self.sounds_grid.addWidget(empty_label, 0, 0)
            return

        for index, sound in enumerate(self.app_config.sounds):
            row = index // self._sound_grid_columns
            column = index % self._sound_grid_columns
            card = SoundCard(
                sound=sound,
                on_play=self.play_sound,
                on_stop=self.stop_sound,
                on_edit=self.edit_sound,
                on_remove=self.remove_sound,
            )
            self.sounds_grid.addWidget(card, row, column)
            card.set_active(sound.id == self.active_sound_id)
            self.sound_cards[sound.id] = card

        self.sounds_grid.setRowStretch((len(self.app_config.sounds) - 1) // self._sound_grid_columns + 1, 1)

    def _configure_grid_columns(self) -> None:
        active_columns = self._sound_grid_columns
        for column in range(MAX_CARD_COLUMNS + 1):
            weight = 1 if column < active_columns else 0
            self.sounds_grid.setColumnStretch(column, weight)

    def _relayout_sound_cards(self) -> None:
        if not self.sound_cards:
            return

        self._configure_grid_columns()
        for index, sound in enumerate(self.app_config.sounds):
            card = self.sound_cards.get(sound.id)
            if card is None:
                continue
            row = index // self._sound_grid_columns
            column = index % self._sound_grid_columns
            self.sounds_grid.addWidget(card, row, column)

    def _update_volume_label(self) -> None:
        self.volume_value_label.setText(f"{int(self.volume_value)}%")

    def _on_volume_changed(self, value: int) -> None:
        self.volume_value = float(value)
        self._update_volume_label()
        self.app_config.global_volume = self.volume_value
        self._save_config()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        current_width = self.width()
        if current_width == self._last_window_width:
            return
        self._last_window_width = current_width

        if self._resize_pending:
            return
        self._resize_pending = True
        QTimer.singleShot(80, self._apply_resize_layout)

    def _apply_resize_layout(self) -> None:
        self._resize_pending = False
        if self.is_closing:
            return

        available_width = max(self.width() - 140, CARD_MIN_WIDTH)
        columns = max(1, min(MAX_CARD_COLUMNS, available_width // CARD_MIN_WIDTH))
        if columns == self._sound_grid_columns:
            return

        self._sound_grid_columns = columns
        self._relayout_sound_cards()

    def add_sound(self) -> None:
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select an audio file",
            "",
            SUPPORTED_FILE_FILTER,
        )
        if not file_path:
            return

        display_name = self._prompt_for_sound_name(
            title="Add sound",
            prompt="Enter a display name or emoji for this sound.",
            initial_value=Path(file_path).stem,
        )
        if display_name is None:
            return

        sound = SoundEntry(file_path=file_path, display_name=display_name)
        self.app_config.sounds.append(sound)
        self._save_config()
        self._render_sound_cards()
        self._set_status(f'Added "{sound.display_name}".')

    def edit_sound(self, sound_id: str) -> None:
        sound = self._get_sound(sound_id)
        if sound is None:
            return

        display_name = self._prompt_for_sound_name(
            title="Edit sound",
            prompt="Update the display name or emoji for this sound.",
            initial_value=sound.display_name,
        )
        if display_name is None:
            return

        sound.display_name = display_name
        self._save_config()
        self._render_sound_cards()
        self._set_status(f'Updated "{sound.display_name}".')

    def remove_sound(self, sound_id: str) -> None:
        sound = self._get_sound(sound_id)
        if sound is None:
            return

        result = QMessageBox.question(
            self,
            "Remove sound",
            f'Are you sure you want to remove "{sound.display_name}" from the board?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        if self.active_sound_id == sound_id and self.player.is_playing():
            self.after_stop_action = lambda current_sound_id=sound_id: self._remove_sound_by_id(
                current_sound_id
            )
            self._set_status(f'Stopping "{sound.display_name}" before removing it...')
            self._stop_current_playback()
            return

        self._remove_sound_by_id(sound_id)

    def play_sound(self, sound_id: str) -> None:
        sound = self._get_sound(sound_id)
        if sound is None:
            return

        if self.player.is_playing():
            if self.active_sound_id == sound_id:
                return

            self.after_stop_action = lambda current_sound_id=sound_id: self._start_sound_by_id(
                current_sound_id
            )
            self._set_status(f'Switching playback to "{sound.display_name}"...')
            self._stop_current_playback()
            return

        self._start_sound_by_id(sound_id)

    def stop_sound(self, sound_id: str) -> None:
        if self.active_sound_id != sound_id or not self.player.is_playing():
            return

        self.after_stop_action = None
        active_sound = self._get_sound(sound_id)
        self._set_status(
            f'Stopping "{active_sound.display_name}"...' if active_sound is not None else "Stopping playback..."
        )
        self._stop_current_playback()

    def _start_sound_by_id(self, sound_id: str) -> None:
        sound = self._get_sound(sound_id)
        if sound is None:
            return

        try:
            self.player.load_audio(sound.file_path)
            virtual_microphone = find_virtual_cable()
            playback_device_index, playback_device_name = find_output_device_index()
            speaker_info = find_default_speaker_index()
            self.previous_microphone_snapshot = snapshot_default_recording_devices()
            set_default_recording_device(virtual_microphone.id)

            device_indices = [playback_device_index]
            speaker_label = "not available"
            if speaker_info is not None:
                speaker_index, speaker_name = speaker_info
                if speaker_index != playback_device_index:
                    device_indices.append(speaker_index)
                    speaker_label = speaker_name

            self.player.play(
                device_indices=device_indices,
                volume=self.volume_value / 100.0,
                on_finished=self.playback_bridge.playback_finished.emit,
                on_error=self.playback_bridge.playback_error.emit,
            )
        except (AudioPlayerError, DeviceManagerError) as exc:
            self.after_stop_action = None
            self._restore_previous_microphone()
            QMessageBox.critical(self, "Playback error", str(exc))
            self._set_status("Playback failed.")
            return
        except Exception as exc:
            self.after_stop_action = None
            self._restore_previous_microphone()
            QMessageBox.critical(self, "Unexpected error", str(exc))
            self._set_status("Playback failed.")
            return

        self.active_sound_id = sound.id
        self._set_status(f'Playing "{sound.display_name}" through VB-Cable...')
        self._set_microphone(f"Current microphone: {virtual_microphone.name}")
        self._set_playback_device(
            f"Virtual playback device: {playback_device_name}\nLocal speaker: {speaker_label}"
        )
        self._refresh_card_states()

    def _stop_current_playback(self) -> None:
        if not self.player.is_playing():
            return

        if self.active_sound_id in self.sound_cards:
            self.sound_cards[self.active_sound_id].stop_button.setEnabled(False)
        self.player.stop()

    def _on_playback_finished(self, interrupted: bool) -> None:
        finished_sound = self._get_sound(self.active_sound_id) if self.active_sound_id else None
        queued_action = self.after_stop_action
        self.after_stop_action = None

        self._restore_previous_microphone()
        self.active_sound_id = None
        self._refresh_card_states()

        if queued_action is not None:
            queued_action()
            return

        if finished_sound is not None and not interrupted:
            self._set_status(f'Finished "{finished_sound.display_name}".')
        else:
            self._set_status("Playback stopped." if interrupted else "Playback finished.")

    def _on_playback_error(self, error: object) -> None:
        self.after_stop_action = None
        self._restore_previous_microphone()
        self.active_sound_id = None
        self._refresh_card_states()
        self._set_status("Playback failed.")
        QMessageBox.critical(self, "Playback error", str(error))

    def _refresh_card_states(self) -> None:
        for sound_id, card in self.sound_cards.items():
            card.set_active(sound_id == self.active_sound_id)

    def _remove_sound_by_id(self, sound_id: str) -> None:
        sounds_before = len(self.app_config.sounds)
        removed_sound = self._get_sound(sound_id)
        self.app_config.sounds = [sound for sound in self.app_config.sounds if sound.id != sound_id]
        if len(self.app_config.sounds) == sounds_before:
            return

        self._save_config()
        self._render_sound_cards()
        removed_name = removed_sound.display_name if removed_sound is not None else "sound"
        self._set_status(f'Removed "{removed_name}".')

    def _prompt_for_sound_name(
        self,
        title: str,
        prompt: str,
        initial_value: str,
    ) -> str | None:
        response, accepted = QInputDialog.getText(self, title, prompt, text=initial_value)
        if not accepted:
            return None

        response = response.strip()
        if not response:
            QMessageBox.warning(self, "Missing name", "Enter a display name or emoji for the sound.")
            return None
        return response

    def _get_sound(self, sound_id: str) -> SoundEntry | None:
        for sound in self.app_config.sounds:
            if sound.id == sound_id:
                return sound
        return None

    def _save_config(self) -> None:
        self.app_config.global_volume = self.volume_value
        save_config(self.app_config)

    def _restore_previous_microphone(self) -> None:
        if not self.previous_microphone_snapshot:
            self._set_microphone(f"Current microphone: {self._safe_current_mic_name()}")
            return

        try:
            restore_default_recording_devices(self.previous_microphone_snapshot)
        except DeviceManagerError as exc:
            QMessageBox.warning(
                self,
                "Microphone restore failed",
                f"Playback stopped, but the previous microphone could not be restored automatically.\n\n{exc}",
            )
        finally:
            self.previous_microphone_snapshot = None
            self._set_microphone(f"Current microphone: {self._safe_current_mic_name()}")

    def _safe_current_mic_name(self) -> str:
        try:
            return get_default_recording_device().name
        except DeviceManagerError:
            return "Unavailable"

    def _set_status(self, text: str) -> None:
        self.status_text = text
        self.status_label.setText(text)

    def _set_microphone(self, text: str) -> None:
        self.microphone_text = text
        self.microphone_label.setText(text)

    def _set_playback_device(self, text: str) -> None:
        self.playback_device_text = text
        self.playback_device_label.setText(text)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.is_closing = True
        self.after_stop_action = None
        self._save_config()
        if self.player.is_playing():
            self.player.stop()
        self._restore_previous_microphone()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    window = DiscordAudioSoundboardApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
