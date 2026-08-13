"""Desktop UI for extracting and organizing ZKTeco attendance logs."""

from __future__ import annotations

import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import zkteco


class DeviceEditor(tk.Toplevel):
    def __init__(self, parent: "DeviceManager", label: str | None, device: dict | None, on_save):
        super().__init__(parent)
        self.on_save = on_save
        self.original_label = label
        self.title("Edit machine" if label else "Add machine")
        self.geometry("430x270")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        data = device or {"ip": "", "port": zkteco.DEFAULT_PORT}
        self.label_var = tk.StringVar(value=label or "")
        self.ip_var = tk.StringVar(value=str(data.get("ip", "")))
        self.port_var = tk.StringVar(value=str(data.get("port", zkteco.DEFAULT_PORT)))

        body = ttk.Frame(self, style="Surface.TFrame", padding=22)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Biometrics machine", style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text="Give the machine a label you will recognize when exporting.", style="Muted.TLabel", wraplength=370).pack(anchor="w", pady=(3, 18))
        fields = ttk.Frame(body, style="Surface.TFrame")
        fields.pack(fill="x")
        ttk.Label(fields, text="Label").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(fields, textvariable=self.label_var).grid(row=0, column=1, sticky="ew", padx=(18, 0), pady=6)
        ttk.Label(fields, text="IP address").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(fields, textvariable=self.ip_var).grid(row=1, column=1, sticky="ew", padx=(18, 0), pady=6)
        ttk.Label(fields, text="Port").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(fields, textvariable=self.port_var).grid(row=2, column=1, sticky="ew", padx=(18, 0), pady=6)
        fields.columnconfigure(1, weight=1)

        actions = ttk.Frame(body, style="Surface.TFrame")
        actions.pack(fill="x", pady=(18, 0))
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Save machine", style="Accent.TButton", command=self.save).pack(side="right", padx=(0, 8))

    def save(self):
        label = self.label_var.get().strip()
        ip = self.ip_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid port", "Port must be a number between 1 and 65535.", parent=self)
            return
        if not label or not ip:
            messagebox.showerror("Missing details", "Label and IP address are required.", parent=self)
            return
        saved = self.on_save(self.original_label, label, {"ip": ip, "port": port})
        if saved is not False:
            self.destroy()


class DeviceManager(tk.Toplevel):
    def __init__(self, parent: "AttendanceApp"):
        super().__init__(parent)
        self.parent_app = parent
        self.title("Manage biometrics machines")
        self.geometry("560x420")
        self.minsize(500, 350)
        self.transient(parent)
        self.grab_set()

        body = ttk.Frame(self, style="Surface.TFrame", padding=22)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Biometrics machines", style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text="The label is shown in the export screen; the IP is stored here.", style="Muted.TLabel").pack(anchor="w", pady=(3, 18))
        table_frame = ttk.Frame(body, style="Surface.TFrame")
        table_frame.pack(fill="both", expand=True)
        self.machines = ttk.Treeview(table_frame, columns=("label", "ip", "port"), show="headings", selectmode="browse")
        self.machines.heading("label", text="Label")
        self.machines.heading("ip", text="IP address")
        self.machines.heading("port", text="Port")
        self.machines.column("label", width=180, anchor="w")
        self.machines.column("ip", width=180, anchor="w")
        self.machines.column("port", width=80, anchor="w")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.machines.yview)
        self.machines.configure(yscrollcommand=scroll.set)
        self.machines.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.machines.bind("<Double-Button-1>", lambda _event: self.edit_selected())
        self.refresh()

        actions = ttk.Frame(body, style="Surface.TFrame")
        actions.pack(fill="x", pady=(18, 0))
        ttk.Button(actions, text="+ Add machine", command=self.add_machine).pack(side="left")
        ttk.Button(actions, text="Edit", command=self.edit_selected).pack(side="right")
        ttk.Button(actions, text="Delete", style="Danger.TButton", command=self.delete_selected).pack(side="right", padx=(0, 7))
        ttk.Button(actions, text="Done", command=self.destroy).pack(side="right", padx=(0, 7))

    def refresh(self):
        self.machines.delete(*self.machines.get_children())
        for label, device in self.parent_app.devices.items():
            self.machines.insert("", "end", values=(label, device.get("ip", ""), device.get("port", zkteco.DEFAULT_PORT)))

    def _selected_label(self) -> str | None:
        selected = self.machines.selection()
        return str(self.machines.item(selected[0], "values")[0]) if selected else None

    def add_machine(self):
        DeviceEditor(self, None, None, self.save_machine)

    def edit_selected(self):
        label = self._selected_label()
        if not label:
            messagebox.showinfo("Select a machine", "Select a machine to edit first.", parent=self)
            return
        DeviceEditor(self, label, self.parent_app.devices[label], self.save_machine)

    def delete_selected(self):
        label = self._selected_label()
        if not label:
            messagebox.showinfo("Select a machine", "Select a machine to delete first.", parent=self)
            return
        if len(self.parent_app.devices) == 1:
            messagebox.showinfo("Cannot delete", "Keep at least one biometrics machine configured.", parent=self)
            return
        if messagebox.askyesno("Delete machine", f"Delete the {label} machine?", parent=self):
            del self.parent_app.devices[label]
            zkteco.save_devices(self.parent_app.devices)
            self.parent_app.refresh_devices()
            self.refresh()

    def save_machine(self, original_label: str | None, new_label: str, device: dict):
        if new_label != original_label and new_label in self.parent_app.devices:
            messagebox.showerror("Label already exists", f"A machine named {new_label} already exists.", parent=self)
            return False
        if original_label and original_label != new_label:
            del self.parent_app.devices[original_label]
        self.parent_app.devices[new_label] = device
        zkteco.save_devices(self.parent_app.devices)
        if self.parent_app.device_var.get() == original_label:
            self.parent_app.device_var.set(new_label)
        self.parent_app.refresh_devices()
        self.refresh()
        return True


class GroupEditor(tk.Toplevel):
    def __init__(self, parent: "AttendanceApp", group_name: str | None, group: dict | None, on_save):
        super().__init__(parent)
        self.parent_app = parent
        self.on_save = on_save
        self.original_name = group_name
        self.title("Edit group" if group_name else "Add group")
        self.geometry("560x520")
        self.minsize(500, 420)
        self.transient(parent)
        self.grab_set()

        data = group or {"file": "attendance_records.csv", "cutoff": "", "members": []}
        self.name_var = tk.StringVar(value=group_name or "")
        self.file_var = tk.StringVar(value=str(data.get("file", "attendance_records.csv")))
        self.cutoff_var = tk.StringVar(value=str(data.get("cutoff", "")))

        body = ttk.Frame(self, style="Surface.TFrame", padding=22)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Group details", style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text="Choose the people whose logs belong in this export.", style="Muted.TLabel").pack(anchor="w", pady=(3, 18))

        fields = ttk.Frame(body, style="Surface.TFrame")
        fields.pack(fill="x")
        ttk.Label(fields, text="Group name").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(fields, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", padx=(16, 0), pady=5)
        ttk.Label(fields, text="CSV filename").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(fields, textvariable=self.file_var).grid(row=1, column=1, sticky="ew", padx=(16, 0), pady=5)
        ttk.Label(fields, text="Include from").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(fields, textvariable=self.cutoff_var).grid(row=2, column=1, sticky="ew", padx=(16, 0), pady=5)
        ttk.Label(fields, text="YYYY-MM-DD, optional", style="Muted.TLabel").grid(row=2, column=2, sticky="w", padx=(8, 0))
        fields.columnconfigure(1, weight=1)

        member_bar = ttk.Frame(body, style="Surface.TFrame")
        member_bar.pack(fill="x", pady=(24, 7))
        ttk.Label(member_bar, text="Included people", style="Section.TLabel").pack(side="left")
        ttk.Button(member_bar, text="+ Add", command=self.add_member).pack(side="right")
        ttk.Button(member_bar, text="Edit", command=self.edit_member).pack(side="right", padx=(0, 7))
        ttk.Button(member_bar, text="Remove", command=self.remove_member).pack(side="right", padx=(0, 7))

        table_frame = ttk.Frame(body, style="Surface.TFrame")
        table_frame.pack(fill="both", expand=True)
        self.members = ttk.Treeview(table_frame, columns=("id", "name"), show="headings", selectmode="browse")
        self.members.heading("id", text="User ID")
        self.members.heading("name", text="Name")
        self.members.column("id", width=110, anchor="w")
        self.members.column("name", width=260, anchor="w")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.members.yview)
        self.members.configure(yscrollcommand=scroll.set)
        self.members.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for member in data.get("members", []):
            if isinstance(member, dict):
                self.members.insert("", "end", values=(member.get("id", ""), member.get("name", "")))

        actions = ttk.Frame(body, style="Surface.TFrame")
        actions.pack(fill="x", pady=(18, 0))
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Save group", style="Accent.TButton", command=self.save).pack(side="right", padx=(0, 8))

    def add_member(self):
        self._member_dialog()

    def edit_member(self):
        selected = self.members.selection()
        if not selected:
            messagebox.showinfo("Select a member", "Select a member to edit first.", parent=self)
            return
        item = selected[0]
        values = self.members.item(item, "values")
        self._member_dialog(item, str(values[0]), str(values[1]))

    def _member_dialog(self, item: str | None = None, current_id: str = "", current_name: str = ""):
        user_id = simpledialog.askstring("User ID", "Enter the device user ID:", initialvalue=current_id, parent=self)
        if user_id is None:
            return
        try:
            user_id = str(int(user_id.strip()))
        except ValueError:
            messagebox.showerror("Invalid ID", "User ID must be a whole number.", parent=self)
            return
        name = simpledialog.askstring("Name", "Enter the name for this ID:", initialvalue=current_name, parent=self)
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showerror("Missing name", "Enter a name for this member.", parent=self)
            return
        if item:
            self.members.item(item, values=(user_id, name))
        else:
            self.members.insert("", "end", values=(user_id, name))

    def remove_member(self):
        selected = self.members.selection()
        if selected:
            self.members.delete(selected[0])

    def save(self):
        name = self.name_var.get().strip()
        filename = self.file_var.get().strip()
        cutoff = self.cutoff_var.get().strip()
        if not name or not filename:
            messagebox.showerror("Missing details", "Group name and CSV filename are required.", parent=self)
            return
        if cutoff:
            if zkteco.coerce_datetime(cutoff) is None or len(cutoff) != 10:
                messagebox.showerror("Invalid date", "Use the YYYY-MM-DD format for Include from.", parent=self)
                return
        members = []
        seen_ids = set()
        for item in self.members.get_children():
            values = self.members.item(item, "values")
            user_id = int(values[0])
            if user_id in seen_ids:
                messagebox.showerror("Duplicate ID", f"User ID {user_id} is listed more than once.", parent=self)
                return
            seen_ids.add(user_id)
            members.append({"id": user_id, "name": values[1]})
        saved = self.on_save(self.original_name, name, {"file": filename, "cutoff": cutoff, "members": members})
        if saved is not False:
            self.destroy()


class AttendanceApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Attendance Console")
        self.geometry("1080x700")
        self.minsize(900, 620)
        self.groups = zkteco.load_groups()
        self.devices = zkteco.load_devices()
        first_device = next(iter(self.devices), "")
        self.device_var = tk.StringVar(value=first_device)
        self.mode_var = tk.StringVar(value="All logs")
        self.output_var = tk.StringVar(value=str(Path.cwd() / "attendance_all.csv"))
        self.status_var = tk.StringVar(value="Ready to connect to the attendance device.")
        self.network_warning_var = tk.StringVar()
        self._build_styles()
        self._build_ui()

    def _build_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        system_font = tkfont.nametofont("TkDefaultFont").actual().get("family", "Helvetica")
        self.system_font = system_font
        self.colors = {
            "background": "#F5F5F7",
            "surface": "#FFFFFF",
            "text": "#1D1D1F",
            "secondary": "#6E6E73",
            "border": "#D2D2D7",
            "blue": "#007AFF",
            "blue_active": "#0066D6",
            "blue_tint": "#E5F1FF",
            "danger": "#C93434",
        }
        self.configure(bg=self.colors["background"])
        style.configure(".", font=(system_font, 13))
        style.configure("TLabel", background=self.colors["background"], foreground=self.colors["text"])
        style.configure("Title.TLabel", background=self.colors["background"], font=(system_font, 28, "bold"), foreground=self.colors["text"])
        style.configure("Subtitle.TLabel", background=self.colors["background"], font=(system_font, 13), foreground=self.colors["secondary"])
        style.configure("Section.TLabel", background=self.colors["background"], font=(system_font, 15, "bold"), foreground=self.colors["text"])
        style.configure("Muted.TLabel", background=self.colors["background"], foreground=self.colors["secondary"])
        style.configure("Card.TFrame", background=self.colors["surface"], relief="solid", borderwidth=1)
        style.configure("Card.TLabel", background=self.colors["surface"], foreground=self.colors["text"])
        style.configure("CardSection.TLabel", background=self.colors["surface"], font=(system_font, 15, "bold"), foreground=self.colors["text"])
        style.configure("CardMuted.TLabel", background=self.colors["surface"], foreground=self.colors["secondary"])
        style.configure("Warning.TLabel", background=self.colors["surface"], foreground="#9A6700", font=(system_font, 12))
        style.configure("Surface.TFrame", background=self.colors["background"])
        style.configure("Surface.TLabel", background=self.colors["background"], foreground=self.colors["text"])
        style.configure("Accent.TButton", font=(system_font, 13, "bold"), foreground="#FFFFFF", background=self.colors["blue"], padding=(16, 9), borderwidth=0)
        style.map("Accent.TButton", background=[("active", self.colors["blue_active"]), ("disabled", "#B8C4D3")])
        style.configure("TButton", font=(system_font, 13), foreground=self.colors["text"], padding=(12, 8), borderwidth=1)
        style.map("TButton", background=[("active", "#E8E8ED")])
        style.configure("Danger.TButton", font=(system_font, 13), foreground=self.colors["danger"], padding=(12, 8))
        style.configure("TEntry", padding=(9, 7), fieldbackground=self.colors["surface"])
        style.configure("TCombobox", padding=(8, 6), fieldbackground=self.colors["surface"])
        style.configure("Treeview", background=self.colors["surface"], fieldbackground=self.colors["surface"], foreground=self.colors["text"], rowheight=34, font=(system_font, 12))
        style.map("Treeview", background=[("selected", self.colors["blue_tint"])], foreground=[("selected", self.colors["text"])])
        style.configure("Treeview.Heading", background="#F2F2F7", foreground=self.colors["secondary"], font=(system_font, 11, "bold"), padding=(8, 8))

    def _build_ui(self):
        self.configure(bg=self.colors["background"])
        header = ttk.Frame(self, style="Surface.TFrame", padding=(40, 32, 40, 22))
        header.pack(fill="x")
        ttk.Label(header, text="Attendance Console", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Extract ZKTeco logs into clean, group-specific CSV files.", style="Subtitle.TLabel").pack(anchor="w", pady=(4, 0))

        connection = ttk.Frame(self, style="Card.TFrame", padding=(22, 18))
        connection.pack(fill="x", padx=40)
        ttk.Label(connection, text="Biometrics machine", style="CardSection.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 12))
        self.device_combo = ttk.Combobox(connection, textvariable=self.device_var, state="readonly", width=30)
        self.device_combo.grid(row=1, column=0, sticky="w", padx=(0, 12))
        self.device_combo.bind("<<ComboboxSelected>>", self._device_changed)
        ttk.Button(connection, text="+ Add machine", command=self.add_device).grid(row=1, column=1, sticky="w")
        ttk.Button(connection, text="Manage machines", command=self.manage_devices).grid(row=1, column=2, sticky="w", padx=(8, 0))
        self.test_connection_button = ttk.Button(connection, text="Test connection", command=self.start_connection_test)
        self.test_connection_button.grid(row=1, column=3, sticky="w", padx=(8, 0))
        ttk.Label(connection, text="Select a label here; the saved IP and port are used automatically.", style="CardMuted.TLabel").grid(row=1, column=4, sticky="w", padx=(18, 0))
        ttk.Label(connection, textvariable=self.network_warning_var, style="Warning.TLabel", wraplength=850).grid(row=2, column=0, columnspan=5, sticky="w", pady=(14, 0))
        connection.columnconfigure(4, weight=1)

        content = ttk.Frame(self, style="Surface.TFrame", padding=(40, 24, 40, 36))
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        extract = ttk.Frame(content, style="Card.TFrame", padding=22)
        extract.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(extract, text="Extract logs", style="CardSection.TLabel").pack(anchor="w")
        ttk.Label(extract, text="Choose which people to include in this export.", style="CardMuted.TLabel").pack(anchor="w", pady=(5, 24))
        ttk.Label(extract, text="Export scope", style="Card.TLabel").pack(anchor="w")
        self.scope_combo = ttk.Combobox(extract, textvariable=self.mode_var, state="readonly")
        self.scope_combo.pack(fill="x", pady=(7, 18))
        self.scope_combo.bind("<<ComboboxSelected>>", self._scope_changed)

        ttk.Label(extract, text="Output CSV", style="Card.TLabel").pack(anchor="w")
        output_row = ttk.Frame(extract, style="Card.TFrame")
        output_row.pack(fill="x", pady=(7, 24))
        ttk.Entry(output_row, textvariable=self.output_var).pack(side="left", fill="x", expand=True)
        ttk.Button(output_row, text="Browse", command=self.browse_output).pack(side="right", padx=(8, 0))
        self.export_button = ttk.Button(extract, text="Extract & export", style="Accent.TButton", command=self.start_export)
        self.export_button.pack(anchor="w")
        ttk.Label(extract, textvariable=self.status_var, style="CardMuted.TLabel", wraplength=550).pack(anchor="w", pady=(20, 0))

        groups_card = ttk.Frame(content, style="Card.TFrame", padding=22)
        groups_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ttk.Label(groups_card, text="Groups", style="CardSection.TLabel").pack(anchor="w")
        ttk.Label(groups_card, text="Maintain the IDs and names for each export.", style="CardMuted.TLabel", wraplength=260).pack(anchor="w", pady=(5, 20))
        self.group_list = tk.Listbox(groups_card, height=10, activestyle="none", bd=0, highlightthickness=1, highlightcolor=self.colors["blue"], highlightbackground=self.colors["border"], selectbackground=self.colors["blue_tint"], selectforeground=self.colors["text"], background=self.colors["surface"], foreground=self.colors["text"], font=(self.system_font, 13), relief="flat")
        self.group_list.pack(fill="both", expand=True)
        self.group_list.bind("<Double-Button-1>", lambda _event: self.edit_selected_group())
        group_actions = ttk.Frame(groups_card, style="Card.TFrame")
        group_actions.pack(fill="x", pady=(14, 0))
        ttk.Button(group_actions, text="+ Add group", command=self.add_group).pack(side="left")
        ttk.Button(group_actions, text="Edit", command=self.edit_selected_group).pack(side="right")
        ttk.Button(group_actions, text="Delete", style="Danger.TButton", command=self.delete_selected_group).pack(side="right", padx=(0, 7))
        self.refresh_devices()
        self.refresh_groups()

    def refresh_groups(self):
        self.group_list.delete(0, "end")
        for name in self.groups:
            self.group_list.insert("end", name)
        self.scope_combo["values"] = ["All logs", *self.groups.keys()]

    def refresh_devices(self):
        labels = list(self.devices)
        self.device_combo["values"] = labels
        if self.device_var.get() not in self.devices:
            self.device_var.set(labels[0] if labels else "")
        self.refresh_network_warning()

    def _device_changed(self, _event=None):
        self.refresh_network_warning()

    def refresh_network_warning(self):
        device = self.devices.get(self.device_var.get())
        if not device:
            self.network_warning_var.set("")
            return
        self.network_warning_var.set(
            zkteco.machine_network_warning(str(device.get("ip", "")), int(device.get("port", zkteco.DEFAULT_PORT))) or ""
        )

    def manage_devices(self):
        DeviceManager(self)

    def add_device(self):
        DeviceEditor(self, None, None, self.save_device)

    def save_device(self, original_label: str | None, new_label: str, device: dict):
        if new_label != original_label and new_label in self.devices:
            messagebox.showerror("Label already exists", f"A machine named {new_label} already exists.", parent=self)
            return False
        if original_label and original_label != new_label:
            del self.devices[original_label]
        self.devices[new_label] = device
        zkteco.save_devices(self.devices)
        self.device_var.set(new_label)
        self.refresh_devices()
        return True

    def _scope_changed(self, _event=None):
        selected = self.mode_var.get()
        if selected == "All logs":
            filename = "attendance_all.csv"
        else:
            filename = self.groups[selected].get("file", f"{selected.lower()}_attendance.csv")
        self.output_var.set(str(Path.cwd() / filename))

    def browse_output(self):
        selected = filedialog.asksaveasfilename(title="Choose export file", defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")], initialfile=Path(self.output_var.get()).name)
        if selected:
            self.output_var.set(selected)

    def start_export(self):
        try:
            device_name = self.device_var.get().strip()
            device = self.devices[device_name]
            ip = str(device["ip"])
            port = int(device.get("port", zkteco.DEFAULT_PORT))
        except (KeyError, TypeError, ValueError):
            messagebox.showerror("Missing machine", "Choose or add a biometrics machine first.", parent=self)
            return
        output = Path(self.output_var.get().strip())
        if not output.name:
            messagebox.showerror("Missing output", "Choose a CSV output file first.", parent=self)
            return
        group_name = None if self.mode_var.get() == "All logs" else self.mode_var.get()
        self.status_var.set("Connecting and reading attendance logs…")
        self._set_connection_controls_enabled(False)
        threading.Thread(target=self._export_worker, args=(group_name, output, ip, port, device_name), daemon=True).start()

    def _set_connection_controls_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.export_button.configure(state=state)
        self.test_connection_button.configure(state=state)

    def _selected_device(self):
        try:
            device_name = self.device_var.get().strip()
            device = self.devices[device_name]
            return device_name, str(device["ip"]), int(device.get("port", zkteco.DEFAULT_PORT))
        except (KeyError, TypeError, ValueError):
            return None

    def start_connection_test(self):
        selected = self._selected_device()
        if not selected:
            messagebox.showerror("Missing machine", "Choose or add a biometrics machine first.", parent=self)
            return
        device_name, ip, _port = selected
        self.status_var.set(f"Testing {device_name}… (up to 3 ping attempts)")
        self._set_connection_controls_enabled(False)
        threading.Thread(target=self._connection_test_worker, args=(device_name, ip), daemon=True).start()

    def _connection_test_worker(self, device_name, ip):
        success = zkteco.ping_machine(ip, attempts=3)
        self.after(0, lambda: self._connection_test_finished(device_name, ip, success))

    def _connection_test_finished(self, device_name, ip, success):
        self._set_connection_controls_enabled(True)
        if success:
            message = f"Connected to {device_name} ({ip}). The machine responded to the connection test."
            self.status_var.set(message)
            messagebox.showinfo("Connection successful", message, parent=self)
        else:
            message = (
                f"Unable to connect to {device_name} ({ip}) after 3 ping attempts.\n\n"
                "Check the machine's IP address, network cable, Wi-Fi, VPN, and firewall. "
                "After making changes, use Test connection again before extracting logs."
            )
            self.status_var.set("Unable to connect to the selected machine.")
            messagebox.showerror("Unable to connect", message, parent=self)

    def _export_worker(self, group_name, output, ip, port, device_name):
        try:
            if not zkteco.ping_machine(ip, attempts=3):
                raise ConnectionError(
                    f"Unable to connect to {device_name} ({ip}) after 3 ping attempts. "
                    "Check the network and use Test connection before extracting logs again."
                )
            count = zkteco.export_group(group_name, output, ip=ip, port=port, groups=self.groups)
            self.after(0, lambda: self._export_finished(f"Exported {count:,} record(s) from {device_name} to {output}"))
        except Exception as exc:
            self.after(0, lambda: self._export_failed(str(exc)))

    def _export_finished(self, message: str):
        self.status_var.set(message)
        self._set_connection_controls_enabled(True)
        messagebox.showinfo("Export complete", message, parent=self)

    def _export_failed(self, message: str):
        self.status_var.set("Export failed. Check the device connection and try again.")
        self._set_connection_controls_enabled(True)
        title = "Unable to connect" if message.startswith("Unable to connect") else "Export failed"
        messagebox.showerror(title, message, parent=self)

    def _selected_group_name(self) -> str | None:
        selected = self.group_list.curselection()
        return self.group_list.get(selected[0]) if selected else None

    def add_group(self):
        GroupEditor(self, None, None, self.save_group)

    def edit_selected_group(self):
        name = self._selected_group_name()
        if not name:
            messagebox.showinfo("Select a group", "Select a group to edit first.", parent=self)
            return
        GroupEditor(self, name, self.groups[name], self.save_group)

    def delete_selected_group(self):
        name = self._selected_group_name()
        if not name:
            messagebox.showinfo("Select a group", "Select a group to delete first.", parent=self)
            return
        if messagebox.askyesno("Delete group", f"Delete the {name} group?", parent=self):
            del self.groups[name]
            zkteco.save_groups(self.groups)
            if self.mode_var.get() == name:
                self.mode_var.set("All logs")
                self._scope_changed()
            self.refresh_groups()

    def save_group(self, original_name: str | None, new_name: str, group: dict):
        if new_name != original_name and new_name in self.groups:
            messagebox.showerror("Group already exists", f"A group named {new_name} already exists.", parent=self)
            return False
        if original_name and original_name != new_name:
            del self.groups[original_name]
        self.groups[new_name] = group
        zkteco.save_groups(self.groups)
        if self.mode_var.get() == original_name:
            self.mode_var.set(new_name)
        self.refresh_groups()
        self._scope_changed()
        return True


if __name__ == "__main__":
    AttendanceApp().mainloop()
