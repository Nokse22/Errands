# Copyright 2023 Vlad Krupinskii <mrvladus@yandex.ru>
# SPDX-License-Identifier: MIT

from errands.lib.sync.providers.caldav import SyncProviderCalDAV
from errands.lib.sync.providers.nextcloud import SyncProviderNextcloud
from gi.repository import Adw, GLib
from errands.lib.gsettings import GSettings
from errands.lib.logging import Log
from errands.utils.data import UserData
from errands.utils.functions import threaded


class Sync:
    provider = None
    window: Adw.ApplicationWindow = None

    @classmethod
    def init(self, window, testing: bool = False) -> None:
        self.window = window
        Log.info("Sync: Initialize sync provider")
        match GSettings.get("sync-provider"):
            case 0:
                Log.info("Sync: Sync disabled")
                UserData.clean_deleted()
            case 1:
                self.provider = SyncProviderNextcloud(
                    window=self.window, testing=testing
                )
            case 2:
                self.provider = SyncProviderCalDAV(window=self.window, testing=testing)

    @classmethod
    @threaded
    def sync(self) -> None:
        """
        Sync tasks without blocking the UI
        """
        if GSettings.get("sync-provider") == 0:
            UserData.clean_deleted()
            GLib.idle_add(self.window.lists.update_ui)
            return
        if not self.provider:
            GLib.idle_add(self.window.lists.sync_indicator.set_visible, True)
            self.init(self.window)
            GLib.idle_add(self.window.lists.sync_indicator.set_visible, False)
        if self.provider and self.provider.can_sync:
            GLib.idle_add(self.window.lists.sync_indicator.set_visible, True)
            self.provider.sync()
            GLib.idle_add(self.window.lists.update_ui)
            GLib.idle_add(self.window.lists.sync_indicator.set_visible, False)

    @classmethod
    def test_connection(self) -> bool:
        self.init(testing=True, window=self.window)
        return self.provider.can_sync
