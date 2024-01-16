# Copyright 2023 Vlad Krupinskii <mrvladus@yandex.ru>
# SPDX-License-Identifier: MIT

from typing import Self
from errands.widgets.components import Box, Button
from gi.repository import Gtk, Adw, Gdk, GObject, GLib
from errands.lib.sync.sync import Sync
from errands.lib.logging import Log
from errands.utils.data import UserData
from errands.utils.markup import Markup
from errands.utils.functions import get_children
from errands.lib.gsettings import GSettings


class Task(Gtk.Revealer):
    just_added: bool = True
    can_sync: bool = True

    def __init__(
        self,
        uid: str,
        list_uid: str,
        window: Adw.ApplicationWindow,
        task_list,
        parent,
        is_sub_task: bool,
    ) -> None:
        super().__init__()
        Log.info(f"Add task: {uid}")

        self.uid = uid
        self.list_uid = list_uid
        self.window = window
        self.task_list = task_list
        self.parent = parent
        self.is_sub_task = is_sub_task
        self.trash = window.trash
        self.details = window.details

        self.build_ui()
        self.add_sub_tasks()
        # Add to trash if needed
        if self.get_prop("trash"):
            self.trash.trash_add(self)
        # Expand
        self.expand(self.get_prop("expanded"))

    def get_prop(self, prop: str):
        res = UserData.get_prop(self.list_uid, self.uid, prop)
        if prop in "deleted completed expanded trash":
            res = bool(res)
        return res

    def update_props(self, props: list[str], values: list):
        UserData.update_props(self.list_uid, self.uid, props, values)

    def build_ui(self):
        # Top drop area
        top_drop_img = Gtk.Image(
            icon_name="list-add-symbolic",
            hexpand=True,
            css_classes=["dim-label", "task-drop-area"],
        )
        top_drop_img_target = Gtk.DropTarget.new(actions=Gdk.DragAction.MOVE, type=Task)
        top_drop_img_target.connect("drop", self.on_task_top_drop)
        top_drop_img.add_controller(top_drop_img_target)
        self.top_drop_area = Gtk.Revealer(child=top_drop_img, transition_type=5)
        # Drop controller
        drop_ctrl = Gtk.DropControllerMotion.new()
        drop_ctrl.bind_property(
            "contains-pointer",
            self.top_drop_area,
            "reveal-child",
            GObject.BindingFlags.SYNC_CREATE,
        )
        self.add_controller(drop_ctrl)

        # Task row
        self.task_row = Adw.ActionRow(
            title=Markup.find_url(Markup.escape(self.get_prop("text"))),
            css_classes=["rounded-corners", "transparent"],
            height_request=60,
            tooltip_text=_("Click for Details"),
            accessible_role=Gtk.AccessibleRole.ROW,
            cursor=Gdk.Cursor.new_from_name("pointer"),
            use_markup=True,
        )

        # Mark as completed button
        self.completed_btn = Gtk.CheckButton(
            valign="center",
            tooltip_text=_("Mark as Completed"),
            css_classes=["selection-mode"],
        )
        self.completed_btn.connect("toggled", self.on_completed_btn_toggled)
        self.completed_btn.set_active(self.get_prop("completed"))
        self.task_row.add_prefix(self.completed_btn)

        # Expand button
        self.expand_btn = Button(
            icon_name="errands-up-symbolic",
            on_click=lambda *_: self.expand(
                not self.sub_tasks_revealer.get_child_revealed()
            ),
            valign="center",
            tooltip_text=_("Expand / Fold"),
            css_classes=["flat", "circular", "fade", "rotate"],
        )

        # Details panel button
        details_btn = Button(
            icon_name="errands-info-symbolic",
            on_click=self.on_details_clicked,
            tooltip_text=_("Details"),
            css_classes=["flat"],
            valign="center",
        )

        GSettings.bind("primary-action-show-sub-tasks", details_btn, "visible")
        GSettings.bind("primary-action-show-sub-tasks", self.expand_btn, "visible", GObject.BindingFlags.INVERT_BOOLEAN)

        suffix_box = Box(
            children=[self.expand_btn, details_btn],
        )

        self.task_row.add_suffix(suffix_box)
        task_row_box = Gtk.ListBox(
            selection_mode=0,
            css_classes=["rounded-corners", "transparent"],
            accessible_role=Gtk.AccessibleRole.PRESENTATION,
        )
        task_row_box.append(self.task_row)

        # Task row controllers
        task_row_drag_source = Gtk.DragSource.new()
        task_row_drag_source.set_actions(Gdk.DragAction.MOVE)
        task_row_drag_source.connect("prepare", self.on_drag_prepare)
        task_row_drag_source.connect("drag-begin", self.on_drag_begin)
        task_row_drag_source.connect("drag-cancel", self.on_drag_end)
        task_row_drag_source.connect("drag-end", self.on_drag_end)
        self.task_row.add_controller(task_row_drag_source)
        task_row_drop_target = Gtk.DropTarget.new(
            actions=Gdk.DragAction.MOVE, type=Task
        )
        task_row_drop_target.connect("drop", self.on_drop)
        self.task_row.add_controller(task_row_drop_target)

        task_row_click_ctrl = Gtk.GestureClick.new()
        task_row_click_ctrl.connect("released", self.on_row_clicked)
        self.task_row.add_controller(task_row_click_ctrl)

        # Sub-tasks entry
        sub_tasks_entry = Gtk.Entry(
            hexpand=True,
            placeholder_text=_("Add new Sub-Task"),
            margin_bottom=6,
            margin_start=12,
            margin_end=12,
        )
        sub_tasks_entry.connect("activate", self.on_sub_task_added)

        # Sub-tasks
        self.tasks_list = Box(orientation="vertical", css_classes=["sub-tasks"])

        # Sub-tasks revealer
        self.sub_tasks_revealer = Gtk.Revealer(
            child=Box(
                children=[sub_tasks_entry, self.tasks_list], orientation="vertical"
            )
        )

        # Task card
        self.main_box = Box(
            children=[task_row_box, self.sub_tasks_revealer],
            orientation="vertical",
            hexpand=True,
            css_classes=["fade", "card", f'task-{self.get_prop("color")}'],
        )

        self.set_child(
            Box(
                children=[self.top_drop_area, self.main_box],
                orientation="vertical",
                margin_start=12,
                margin_end=12,
                margin_bottom=6,
                margin_top=6,
            )
        )

    def add_task(self, uid: str) -> Self:
        new_task = Task(uid, self.list_uid, self.window, self.task_list, self, True)
        self.tasks_list.append(new_task)
        new_task.toggle_visibility(not new_task.get_prop("trash"))
        return new_task

    def add_sub_tasks(self) -> None:
        subs = UserData.get_sub_tasks_uids(self.list_uid, self.uid)
        if len(subs) == 0:
            self.just_added = False
            return
        for uid in subs:
            self.add_task(uid)
        self.update_status()
        self.parent.update_status()
        self.task_list.update_status()
        self.just_added = False

    def delete(self, *_) -> None:
        Log.info(f"Task: Move to trash: '{self.uid}'")

        self.toggle_visibility(False)
        self.update_props(["trash"], [True])
        self.completed_btn.set_active(True)
        self.trash.trash_add(self)
        for task in get_children(self.tasks_list):
            if not task.get_prop("trash"):
                task.delete()
        self.details.status.set_visible(True)
        self.parent.update_status()

    def expand(self, expanded: bool) -> None:
        self.sub_tasks_revealer.set_reveal_child(expanded)
        self.update_props(["expanded"], [expanded])
        if expanded:
            self.expand_btn.remove_css_class("rotate")
        else:
            self.expand_btn.add_css_class("rotate")

    def purge(self) -> None:
        """
        Completely remove widget
        """

        self.parent.tasks_list.remove(self)
        self.run_dispose()

    def toggle_visibility(self, on: bool) -> None:
        self.set_reveal_child(on)

    def update_status(self) -> None:
        # n_total: int = UserData.run_sql(
        #     f"""SELECT COUNT(*) FROM tasks
        #     WHERE parent = '{self.uid}'
        #     AND trash = 0
        #     AND deleted = 0
        #     AND list_uid = '{self.list_uid}'""",
        #     fetch=True,
        # )[0][0]
        # n_completed: int = UserData.run_sql(
        #     f"""SELECT COUNT(*) FROM tasks
        #     WHERE parent = '{self.uid}'
        #     AND completed = 1
        #     AND deleted = 0
        #     AND trash = 0
        #     AND list_uid = '{self.list_uid}'""",
        #     fetch=True,
        # )[0][0]
        # self.task_row.set_subtitle(
        #     _("Completed:") + f" {n_completed} / {n_total}"  # pyright: ignore
        #     if n_total > 0
        #     else ""
        # )
        sub_tasks: list[Task] = [
            t for t in get_children(self.tasks_list) if t.get_reveal_child()
        ]
        n_total: int = len(sub_tasks)
        n_completed: int = len([t for t in sub_tasks if t.completed_btn.get_active()])
        self.update_props(
            ["percent_complete"], [n_completed / n_total * 100 if n_total > 0 else 0]
        )
        self.task_row.set_subtitle(
            _("Completed:") + f" {n_completed} / {n_total}" if n_total > 0 else ""
        )

    def on_completed_btn_toggled(self, btn: Gtk.ToggleButton) -> None:
        """
        Toggle check button and add style to the text
        """

        Log.info(f"Task: Set completed to '{btn.get_active()}'")

        def _set_crossline():
            if btn.get_active():
                self.task_row.add_css_class("task-completed")
            else:
                self.task_row.remove_css_class("task-completed")

        # If task is just added set crossline and return to avoid sync loop
        _set_crossline()
        if self.just_added:
            return

        # Get visible sub-tasks
        sub_tasks: list[Task] = [
            t for t in get_children(self.tasks_list) if t.get_reveal_child()
        ]

        # Complete sub-tasks, but not uncomplete
        if btn.get_active():
            for task in sub_tasks:
                task.can_sync = False
                task.completed_btn.set_active(True)
                task.can_sync = True
            self.update_status()

        # Uncomplete parent if sub-task is uncompleted
        if self.get_prop("parent"):
            if not btn.get_active():
                self.parent.completed_btn.set_active(False)
            self.parent.update_status()

        # Update data
        self.update_props(["completed", "synced"], [btn.get_active(), False])

        # Sync
        if self.can_sync:
            self.task_list.update_status()
            Sync.sync()

    def on_row_clicked(self, *args) -> None:
        # Show sub-tasks if this is primary action
        if GSettings.get("primary-action-show-sub-tasks"):
            self.expand(not self.sub_tasks_revealer.get_child_revealed())
        else:
            self.on_details_clicked()

    def on_details_clicked(self, *args) -> None:
        # Close details on second click
        if (
            self.details.parent == self
            and not self.details.status.get_visible()
            and self.window.split_view_inner.get_show_sidebar()
        ):
            self.window.split_view_inner.set_show_sidebar(False)
            return
        # Update details and show sidebar
        self.details.update_info(self)
        self.window.split_view_inner.set_show_sidebar(True)

    def on_sub_task_added(self, entry: Gtk.Entry) -> None:
        """
        Add new Sub-Task
        """
        text: str = entry.get_buffer().props.text
        # Return if entry is empty
        if text.strip(" \n\t") == "":
            return
        # Add sub-task
        self.add_task(
            UserData.add_task(list_uid=self.list_uid, text=text, parent=self.uid)
        )
        # Clear entry
        entry.get_buffer().props.text = ""
        # Update status
        self.update_props(["completed"], [False])
        self.just_added = True
        self.completed_btn.set_active(False)
        self.just_added = False
        self.update_status()
        # Sync
        Sync.sync()

    # --- Drag and Drop --- #

    def on_drag_end(self, *_) -> bool:
        self.set_sensitive(True)
        # KDE dnd bug workaround for issue #111
        for task in self.task_list.get_all_tasks():
            task.top_drop_area.set_reveal_child(False)

    def on_drag_begin(self, _, drag) -> bool:
        text = self.get_prop("text")
        icon: Gtk.DragIcon = Gtk.DragIcon.get_for_drag(drag)
        icon.set_child(Gtk.Button(label=text if len(text) < 20 else f"{text[0:20]}..."))

    def on_drag_prepare(self, *_) -> Gdk.ContentProvider:
        self.set_sensitive(False)
        value = GObject.Value(Task)
        value.set_object(self)
        return Gdk.ContentProvider.new_for_value(value)

    def on_task_top_drop(self, _drop, task, _x, _y) -> bool:
        """
        When task is dropped on "+" area on top of task
        """

        # Return if task is itself
        if task == self:
            return False
        # Move data
        UserData.run_sql("CREATE TABLE tmp AS SELECT * FROM tasks WHERE 0")
        ids = UserData.get_tasks()
        ids.insert(ids.index(self.uid), ids.pop(ids.index(task.uid)))
        for id in ids:
            UserData.run_sql(f"INSERT INTO tmp SELECT * FROM tasks WHERE uid = '{id}'")
        UserData.run_sql("DROP TABLE tasks", "ALTER TABLE tmp RENAME TO tasks")
        # If task has the same parent
        if task.parent == self.parent:
            # Move widget
            self.parent.tasks_list.reorder_child_after(task, self)
            self.parent.tasks_list.reorder_child_after(self, task)
            return True
        # Change parent if different parents
        task.update_props(["parent", "synced"], [self.get_prop("parent"), False])
        task.purge()
        # Add new task widget
        new_task = Task(
            task.uid,
            self.list_uid,
            self.window,
            self.task_list,
            self.parent,
            self.get_prop("parent") != None,
        )
        self.parent.tasks_list.append(new_task)
        self.parent.tasks_list.reorder_child_after(new_task, self)
        self.parent.tasks_list.reorder_child_after(self, new_task)
        new_task.toggle_visibility(True)
        self.details.update_info(new_task)
        # Update status
        self.parent.update_status()
        task.parent.update_status()
        # Sync
        Sync.sync()

        return True

    def on_drop(self, _drop, task: Self, _x, _y) -> None:
        """
        When task is dropped on task and becomes sub-task
        """

        if task == self or task.parent == self:
            return

        # Change parent
        task.update_props(["parent", "synced"], [self.get_prop("uid"), False])
        # Move data
        uids = UserData.get_tasks()
        last_sub_uid = UserData.get_sub_tasks_uids(self.list_uid, self.uid)[-1]
        uids.insert(
            uids.index(self.uid) + uids.index(last_sub_uid),
            uids.pop(uids.index(task.uid)),
        )
        UserData.run_sql("CREATE TABLE tmp AS SELECT * FROM tasks WHERE 0")
        for id in uids:
            UserData.run_sql(f"INSERT INTO tmp SELECT * FROM tasks WHERE uid = '{id}'")
        UserData.run_sql("DROP TABLE tasks", "ALTER TABLE tmp RENAME TO tasks")
        # Remove old task
        task.purge()
        # Add new sub-task
        new_task = self.add_task(task.uid)
        self.details.update_info(new_task)
        self.update_props(["completed"], [False])
        self.just_added = True
        self.completed_btn.set_active(False)
        self.just_added = False
        # Update status
        task.parent.update_status()
        self.update_status()
        self.parent.update_status()
        # Sync
        Sync.sync()

        return True
