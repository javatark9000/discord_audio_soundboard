from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk

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


SUPPORTED_FILE_TYPES = [
    ("Audio files", "*.mp3 *.wav *.ogg *.flac *.aac *.m4a"),
    ("All files", "*.*"),
]
DEFAULT_CARD_COLUMNS = 3
MAX_CARD_COLUMNS = 4
CARD_MIN_WIDTH = 220


class SoundCard(ctk.CTkFrame):
    def __init__(
        self,
        master,
        sound: SoundEntry,
        on_play: Callable[[str], None],
        on_stop: Callable[[str], None],
        on_edit: Callable[[str], None],
        on_remove: Callable[[str], None],
    ) -> None:
        super().__init__(master, corner_radius=16, border_width=1)
        self.sound = sound
        self._default_border_color = self.cget("border_color")
        self._default_fg_color = self.cget("fg_color")

        self.grid_columnconfigure(0, weight=1)

        self.name_label = ctk.CTkLabel(
            self,
            text=sound.display_name,
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        )
        self.name_label.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 6))

        self.file_label = ctk.CTkLabel(
            self,
            text=Path(sound.file_path).name,
            anchor="w",
            justify="left",
            text_color=("gray35", "gray75"),
        )
        self.file_label.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        controls_frame.grid_columnconfigure(0, weight=1)
        controls_frame.grid_columnconfigure(1, weight=1)

        self.play_button = ctk.CTkButton(
            controls_frame,
            text="Play",
            command=lambda: on_play(self.sound.id),
        )
        self.play_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 8))

        self.stop_button = ctk.CTkButton(
            controls_frame,
            text="Stop",
            fg_color="#9b1c1c",
            hover_color="#7f1d1d",
            state="disabled",
            command=lambda: on_stop(self.sound.id),
        )
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 8))

        self.edit_button = ctk.CTkButton(
            controls_frame,
            text="Edit",
            fg_color="transparent",
            border_width=1,
            command=lambda: on_edit(self.sound.id),
        )
        self.edit_button.grid(row=1, column=0, sticky="ew", padx=(0, 6))

        self.remove_button = ctk.CTkButton(
            controls_frame,
            text="Remove",
            fg_color="transparent",
            border_width=1,
            command=lambda: on_remove(self.sound.id),
        )
        self.remove_button.grid(row=1, column=1, sticky="ew", padx=(6, 0))

    def update_sound(self, sound: SoundEntry) -> None:
        self.sound = sound
        self.name_label.configure(text=sound.display_name)
        self.file_label.configure(text=Path(sound.file_path).name)

    def set_active(self, active: bool) -> None:
        self.configure(
            border_width=2 if active else 1,
            border_color="#2563eb" if active else self._default_border_color,
            fg_color=("#dbeafe", "#1f2937") if active else self._default_fg_color,
        )
        self.play_button.configure(state="disabled" if active else "normal")
        self.stop_button.configure(state="normal" if active else "disabled")


class DiscordAudioSoundboardApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Discord Audio Soundboard")
        self.geometry("900x600")
        self.minsize(760, 500)

        self.player = AudioPlayer()
        self.app_config = load_config()
        self.sound_cards: dict[str, SoundCard] = {}
        self.previous_microphone_snapshot: dict[str, str] | None = None
        self.active_sound_id: str | None = None
        self.after_stop_action: Callable[[], None] | None = None
        self.is_closing = False
        self._sound_grid_columns = DEFAULT_CARD_COLUMNS
        self._resize_after_id: str | None = None
        self._last_window_width: int = 0

        current_mic_name = self._safe_current_mic_name()

        self.status_var = tk.StringVar(value="Ready")
        self.microphone_var = tk.StringVar(value=f"Current microphone: {current_mic_name}")
        self.playback_device_var = tk.StringVar(value="Virtual playback device: not resolved yet")
        self.volume_var = tk.DoubleVar(value=self.app_config.global_volume)
        self.volume_text_var = tk.StringVar()

        self._build_ui()
        self._update_volume_label()
        self._render_sound_cards()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_window_resize)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(self, corner_radius=18)
        container.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(3, weight=1)

        title = ctk.CTkLabel(
            container,
            text="Discord Audio Soundboard",
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=24, pady=(24, 12))

        description = ctk.CTkLabel(
            container,
            text="Save your sounds locally, label them with text or emoji, and play them through VB-Cable.",
            anchor="w",
            justify="left",
        )
        description.grid(row=1, column=0, sticky="ew", padx=24)

        toolbar = ctk.CTkFrame(container)
        toolbar.grid(row=2, column=0, sticky="ew", padx=24, pady=(20, 12))
        toolbar.grid_columnconfigure(1, weight=1)

        add_sound_button = ctk.CTkButton(
            toolbar,
            text="Add Sound",
            width=150,
            command=self.add_sound,
        )
        add_sound_button.grid(row=0, column=0, padx=18, pady=18, sticky="w")

        volume_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        volume_frame.grid(row=0, column=1, sticky="ew", padx=(0, 18), pady=18)
        volume_frame.grid_columnconfigure(0, weight=1)

        volume_label = ctk.CTkLabel(
            volume_frame,
            text="Playback volume",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        volume_label.grid(row=0, column=0, sticky="w")

        volume_value = ctk.CTkLabel(volume_frame, textvariable=self.volume_text_var)
        volume_value.grid(row=0, column=1, sticky="e", padx=(12, 0))

        volume_slider = ctk.CTkSlider(
            volume_frame,
            from_=0,
            to=100,
            variable=self.volume_var,
            number_of_steps=100,
            command=self._on_volume_changed,
        )
        volume_slider.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.sounds_frame = ctk.CTkScrollableFrame(
            container,
            label_text="Sounds",
            corner_radius=16,
        )
        self.sounds_frame.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 12))

        status_frame = ctk.CTkFrame(container)
        status_frame.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 24))
        status_frame.grid_columnconfigure(0, weight=1)

        status_label = ctk.CTkLabel(
            status_frame,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
            justify="left",
        )
        status_label.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 8))

        mic_label = ctk.CTkLabel(status_frame, textvariable=self.microphone_var, anchor="w")
        mic_label.grid(row=1, column=0, sticky="ew", padx=18, pady=4)

        playback_label = ctk.CTkLabel(
            status_frame,
            textvariable=self.playback_device_var,
            anchor="w",
            justify="left",
        )
        playback_label.grid(row=2, column=0, sticky="ew", padx=18, pady=(4, 16))

    def _render_sound_cards(self) -> None:
        for widget in self.sounds_frame.winfo_children():
            widget.destroy()

        self.sound_cards.clear()

        self._configure_grid_columns()

        if not self.app_config.sounds:
            empty_label = ctk.CTkLabel(
                self.sounds_frame,
                text="No sounds saved yet. Use Add Sound to build your board.",
                justify="center",
            )
            empty_label.grid(row=0, column=0, padx=12, pady=24, sticky="ew")
            return

        for index, sound in enumerate(self.app_config.sounds):
            row = index // self._sound_grid_columns
            column = index % self._sound_grid_columns
            card = SoundCard(
                self.sounds_frame,
                sound=sound,
                on_play=self.play_sound,
                on_stop=self.stop_sound,
                on_edit=self.edit_sound,
                on_remove=self.remove_sound,
            )
            card.grid(row=row, column=column, sticky="nsew", padx=10, pady=10)
            card.set_active(sound.id == self.active_sound_id)
            self.sound_cards[sound.id] = card

    def _configure_grid_columns(self) -> None:
        active_columns = self._sound_grid_columns
        for column in range(MAX_CARD_COLUMNS + 1):
            weight = 1 if column < active_columns else 0
            self.sounds_frame.grid_columnconfigure(column, weight=weight)

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
            card.grid_configure(row=row, column=column)

    def _update_volume_label(self) -> None:
        self.volume_text_var.set(f"{int(self.volume_var.get())}%")

    def _on_volume_changed(self, _value: float) -> None:
        self._update_volume_label()
        self.app_config.global_volume = self.volume_var.get()
        self._save_config()

    def _on_window_resize(self, _event) -> None:
        if _event.widget is not self:
            return

        current_width = self.winfo_width()
        if current_width == self._last_window_width:
            return
        self._last_window_width = current_width

        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except tk.TclError:
                pass
        self._resize_after_id = self.after(80, self._apply_resize_layout)

    def _apply_resize_layout(self) -> None:
        self._resize_after_id = None
        if self.is_closing:
            return

        available_width = max(self.winfo_width() - 140, CARD_MIN_WIDTH)
        columns = max(1, min(MAX_CARD_COLUMNS, available_width // CARD_MIN_WIDTH))
        if columns == self._sound_grid_columns:
            return

        self._sound_grid_columns = columns
        self._relayout_sound_cards()

    def _schedule_callback(self, callback, *args) -> None:
        if self.is_closing:
            return

        try:
            self.after(0, callback, *args)
        except tk.TclError:
            return

    def add_sound(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select an audio file",
            filetypes=SUPPORTED_FILE_TYPES,
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
        self.status_var.set(f'Added "{sound.display_name}".')

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
        self.status_var.set(f'Updated "{sound.display_name}".')

    def remove_sound(self, sound_id: str) -> None:
        sound = self._get_sound(sound_id)
        if sound is None:
            return

        confirmed = messagebox.askyesno(
            "Remove sound",
            f'Are you sure you want to remove "{sound.display_name}" from the board?',
            parent=self,
        )
        if not confirmed:
            return

        if self.active_sound_id == sound_id and self.player.is_playing():
            self.after_stop_action = lambda current_sound_id=sound_id: self._remove_sound_by_id(
                current_sound_id
            )
            self.status_var.set(f'Stopping "{sound.display_name}" before removing it...')
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
            self.status_var.set(f'Switching playback to "{sound.display_name}"...')
            self._stop_current_playback()
            return

        self._start_sound_by_id(sound_id)

    def stop_sound(self, sound_id: str) -> None:
        if self.active_sound_id != sound_id or not self.player.is_playing():
            return

        self.after_stop_action = None
        active_sound = self._get_sound(sound_id)
        self.status_var.set(
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
                volume=self.volume_var.get() / 100.0,
                on_finished=lambda interrupted: self._schedule_callback(
                    self._on_playback_finished, interrupted
                ),
                on_error=lambda exc: self._schedule_callback(self._on_playback_error, exc),
            )
        except (AudioPlayerError, DeviceManagerError) as exc:
            self.after_stop_action = None
            self._restore_previous_microphone()
            messagebox.showerror("Playback error", str(exc), parent=self)
            self.status_var.set("Playback failed.")
            return
        except Exception as exc:
            self.after_stop_action = None
            self._restore_previous_microphone()
            messagebox.showerror("Unexpected error", str(exc), parent=self)
            self.status_var.set("Playback failed.")
            return

        self.active_sound_id = sound.id
        self.status_var.set(f'Playing "{sound.display_name}" through VB-Cable...')
        self.microphone_var.set(f"Current microphone: {virtual_microphone.name}")
        self.playback_device_var.set(
            f"Virtual playback device: {playback_device_name}\nLocal speaker: {speaker_label}"
        )
        self._refresh_card_states()

    def _stop_current_playback(self) -> None:
        if not self.player.is_playing():
            return

        if self.active_sound_id in self.sound_cards:
            self.sound_cards[self.active_sound_id].stop_button.configure(state="disabled")
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
            self.status_var.set(f'Finished "{finished_sound.display_name}".')
        else:
            self.status_var.set("Playback stopped." if interrupted else "Playback finished.")

    def _on_playback_error(self, error: Exception) -> None:
        self.after_stop_action = None
        self._restore_previous_microphone()
        self.active_sound_id = None
        self._refresh_card_states()
        self.status_var.set("Playback failed.")
        messagebox.showerror("Playback error", str(error), parent=self)

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
        self.status_var.set(f'Removed "{removed_name}".')

    def _prompt_for_sound_name(
        self,
        title: str,
        prompt: str,
        initial_value: str,
    ) -> str | None:
        response = simpledialog.askstring(
            title,
            prompt,
            parent=self,
            initialvalue=initial_value,
        )
        if response is None:
            return None

        response = response.strip()
        if not response:
            messagebox.showwarning(
                "Missing name",
                "Enter a display name or emoji for the sound.",
                parent=self,
            )
            return None
        return response

    def _get_sound(self, sound_id: str) -> SoundEntry | None:
        for sound in self.app_config.sounds:
            if sound.id == sound_id:
                return sound
        return None

    def _save_config(self) -> None:
        self.app_config.global_volume = self.volume_var.get()
        save_config(self.app_config)

    def _restore_previous_microphone(self) -> None:
        if not self.previous_microphone_snapshot:
            self.microphone_var.set(f"Current microphone: {self._safe_current_mic_name()}")
            return

        try:
            restore_default_recording_devices(self.previous_microphone_snapshot)
        except DeviceManagerError as exc:
            messagebox.showwarning(
                "Microphone restore failed",
                f"Playback stopped, but the previous microphone could not be restored automatically.\n\n{exc}",
                parent=self,
            )
        finally:
            self.previous_microphone_snapshot = None
            self.microphone_var.set(f"Current microphone: {self._safe_current_mic_name()}")

    def _safe_current_mic_name(self) -> str:
        try:
            return get_default_recording_device().name
        except DeviceManagerError:
            return "Unavailable"

    def _on_close(self) -> None:
        self.is_closing = True
        self.after_stop_action = None
        self._save_config()
        if self.player.is_playing():
            self.player.stop()
        self._restore_previous_microphone()
        self.destroy()


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = DiscordAudioSoundboardApp()
    app.mainloop()


if __name__ == "__main__":
    main()
