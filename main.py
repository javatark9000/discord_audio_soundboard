from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from audio_player import AudioPlayer, AudioPlayerError, find_output_device_index
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


class DiscordAudioSoundboardApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Discord Audio Soundboard")
        self.geometry("760x440")
        self.minsize(720, 420)

        self.player = AudioPlayer()
        self.selected_file: str | None = None
        self.previous_microphone_snapshot: dict[str, str] | None = None
        self.is_closing = False

        current_mic_name = self._safe_current_mic_name()

        self.file_label_var = tk.StringVar(value="No audio file selected")
        self.status_var = tk.StringVar(value="Ready")
        self.microphone_var = tk.StringVar(value=f"Current microphone: {current_mic_name}")
        self.playback_device_var = tk.StringVar(value="Virtual playback device: not resolved yet")
        self.volume_var = tk.DoubleVar(value=80.0)
        self.volume_text_var = tk.StringVar(value="80%")
        self.volume_var.trace_add("write", self._update_volume_label)

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(self, corner_radius=18)
        container.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
        container.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            container,
            text="Discord Audio Soundboard",
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=24, pady=(24, 12))

        description = ctk.CTkLabel(
            container,
            text="Route a selected audio file through VB-Cable and restore your previous microphone automatically.",
            anchor="w",
            justify="left",
        )
        description.grid(row=1, column=0, sticky="ew", padx=24)

        file_frame = ctk.CTkFrame(container, fg_color="transparent")
        file_frame.grid(row=2, column=0, sticky="ew", padx=24, pady=(24, 16))
        file_frame.grid_columnconfigure(1, weight=1)

        select_button = ctk.CTkButton(
            file_frame,
            text="Select Audio",
            width=150,
            command=self.select_audio_file,
        )
        select_button.grid(row=0, column=0, padx=(0, 12), pady=4, sticky="w")

        file_label = ctk.CTkLabel(
            file_frame,
            textvariable=self.file_label_var,
            anchor="w",
            justify="left",
        )
        file_label.grid(row=0, column=1, sticky="ew")

        controls_frame = ctk.CTkFrame(container)
        controls_frame.grid(row=3, column=0, sticky="ew", padx=24, pady=8)
        controls_frame.grid_columnconfigure(0, weight=1)
        controls_frame.grid_columnconfigure(1, weight=1)

        self.play_button = ctk.CTkButton(
            controls_frame,
            text="Play",
            height=52,
            state="disabled",
            command=self.play_selected_audio,
        )
        self.play_button.grid(row=0, column=0, sticky="ew", padx=(18, 9), pady=18)

        self.stop_button = ctk.CTkButton(
            controls_frame,
            text="Stop",
            height=52,
            fg_color="#9b1c1c",
            hover_color="#7f1d1d",
            state="disabled",
            command=self.stop_audio,
        )
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(9, 18), pady=18)

        volume_frame = ctk.CTkFrame(container)
        volume_frame.grid(row=4, column=0, sticky="ew", padx=24, pady=(8, 12))
        volume_frame.grid_columnconfigure(0, weight=1)

        volume_label = ctk.CTkLabel(
            volume_frame,
            text="Playback volume",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        volume_label.grid(row=0, column=0, sticky="w", padx=18, pady=(16, 8))

        volume_slider = ctk.CTkSlider(
            volume_frame,
            from_=0,
            to=100,
            variable=self.volume_var,
            number_of_steps=100,
        )
        volume_slider.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))

        volume_value = ctk.CTkLabel(volume_frame, textvariable=self.volume_text_var)
        volume_value.grid(row=2, column=0, sticky="e", padx=18, pady=(0, 16))

        status_frame = ctk.CTkFrame(container)
        status_frame.grid(row=5, column=0, sticky="ew", padx=24, pady=(8, 24))
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

    def _update_volume_label(self, *_args) -> None:
        self.volume_text_var.set(f"{int(self.volume_var.get())}%")

    def _schedule_callback(self, callback, *args) -> None:
        if self.is_closing:
            return

        try:
            self.after(0, callback, *args)
        except tk.TclError:
            return

    def select_audio_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select an audio file",
            filetypes=SUPPORTED_FILE_TYPES,
        )
        if not file_path:
            return

        self.selected_file = file_path
        self.file_label_var.set(Path(file_path).name)
        self.status_var.set("Audio file selected. Ready to play.")
        self.play_button.configure(state="normal")

    def play_selected_audio(self) -> None:
        if not self.selected_file:
            messagebox.showwarning("Missing audio", "Select an audio file before pressing Play.")
            return

        if self.player.is_playing():
            messagebox.showinfo("Playback in progress", "An audio file is already playing.")
            return

        try:
            self.player.load_audio(self.selected_file)
            virtual_microphone = find_virtual_cable()
            playback_device_index, playback_device_name = find_output_device_index()
            self.previous_microphone_snapshot = snapshot_default_recording_devices()
            set_default_recording_device(virtual_microphone.id)
            self.player.play(
                device_index=playback_device_index,
                volume=self.volume_var.get() / 100.0,
                on_finished=lambda interrupted: self._schedule_callback(
                    self._on_playback_finished, interrupted
                ),
                on_error=lambda exc: self._schedule_callback(self._on_playback_error, exc),
            )
        except (AudioPlayerError, DeviceManagerError) as exc:
            self._restore_previous_microphone()
            messagebox.showerror("Playback error", str(exc))
            return
        except Exception as exc:
            self._restore_previous_microphone()
            messagebox.showerror("Unexpected error", str(exc))
            return

        self.play_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_var.set("Playing audio through VB-Cable...")
        self.microphone_var.set(f"Current microphone: {virtual_microphone.name}")
        self.playback_device_var.set(f"Virtual playback device: {playback_device_name}")

    def stop_audio(self) -> None:
        if not self.player.is_playing():
            return

        self.status_var.set("Stopping playback...")
        self.stop_button.configure(state="disabled")
        self.player.stop()

    def _on_playback_finished(self, interrupted: bool) -> None:
        self._restore_previous_microphone()
        self.play_button.configure(state="normal" if self.selected_file else "disabled")
        self.stop_button.configure(state="disabled")
        self.status_var.set("Playback stopped." if interrupted else "Playback finished.")

    def _on_playback_error(self, error: Exception) -> None:
        self._restore_previous_microphone()
        self.play_button.configure(state="normal" if self.selected_file else "disabled")
        self.stop_button.configure(state="disabled")
        self.status_var.set("Playback failed.")
        messagebox.showerror("Playback error", str(error))

    def _restore_previous_microphone(self) -> None:
        if not self.previous_microphone_snapshot:
            self.microphone_var.set(
                f"Current microphone: {self._safe_current_mic_name()}"
            )
            return

        try:
            restore_default_recording_devices(self.previous_microphone_snapshot)
        except DeviceManagerError as exc:
            messagebox.showwarning(
                "Microphone restore failed",
                f"Playback stopped, but the previous microphone could not be restored automatically.\n\n{exc}",
            )
        finally:
            self.previous_microphone_snapshot = None
            self.microphone_var.set(
                f"Current microphone: {self._safe_current_mic_name()}"
            )

    def _safe_current_mic_name(self) -> str:
        try:
            return get_default_recording_device().name
        except DeviceManagerError:
            return "Unavailable"

    def _on_close(self) -> None:
        self.is_closing = True
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
