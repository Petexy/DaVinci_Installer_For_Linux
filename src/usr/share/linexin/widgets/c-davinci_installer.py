#!/usr/bin/env python3
import gi
import subprocess
import threading
import gettext
import locale
import os
import shutil
import shlex
import re
import glob
import tempfile

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk

APP_NAME = "davinci-installer"
LOCALE_DIR = "/usr/share/locale"

try:
    locale.setlocale(locale.LC_ALL, '')
    lang, encoding = locale.getlocale()
    if lang is None:
        lang = 'en'
except locale.Error:
    lang = 'en'

try:
    _
except NameError:
    gettext.bindtextdomain(APP_NAME, LOCALE_DIR)
    gettext.textdomain(APP_NAME)
    translation = gettext.translation(APP_NAME, LOCALE_DIR, languages=[lang], fallback=True)
    translation.install()
    _ = gettext.gettext

RESOLVE_DIR = "/opt/resolve"
RESOLVE_BIN = os.path.join(RESOLVE_DIR, "bin", "resolve")
SCREENSHOTS_DIR = "/usr/share/linexin/widgets/screenshots"


class DaVinciInstallerWidget(Gtk.Box):
    def __init__(self, hide_sidebar=False, window=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.widgetname = _("DaVinci Installer")
        self.widgeticon = "/usr/share/icons/github.petexy.davinciinstaller.png"
        self.set_margin_top(12)
        self.set_margin_bottom(48)
        self.set_margin_start(48)
        self.set_margin_end(48)

        self.window = window
        self.hide_sidebar = hide_sidebar
        self.install_started = False
        self.error_message = None
        self.user_password = None
        self.progress_data = ""
        self.total_steps = 3
        self.current_product = "DaVinci Resolve"
        self.tmp_build_dir = None
        self.original_run_file_path = None
        self.current_screenshot_idx = 0
        self.screenshots = self._load_screenshots()

        self._apply_css()
        self._build_header()
        self._build_content_stack()

        if self._is_installed():
            self._set_state_post_install()
        else:
            self._set_state_pre_install()

        if hide_sidebar:
            GLib.idle_add(self._resize_window)

    # ── Initialization helpers ──────────────────────────────────────

    def _resize_window(self):
        if self.window:
            try:
                self.window.set_default_size(800, 600)
            except Exception:
                pass
        return False

    @staticmethod
    def _load_screenshots():
        pattern = os.path.join(SCREENSHOTS_DIR, "davinci*.png")
        return sorted(glob.glob(pattern))

    def _apply_css(self):
        css = b"""
.screenshot-bg-davinci {
    background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460);
    border-radius: 12px;
    padding: 24px;
    min-height: 300px;
}
"""
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── UI construction ─────────────────────────────────────────────

    def _build_header(self):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.set_margin_bottom(12)

        icon = Gtk.Image()
        if os.path.exists(self.widgeticon):
            icon.set_from_file(self.widgeticon)
        else:
            icon.set_from_icon_name("package-x-generic")
        icon.set_pixel_size(48)
        header.append(icon)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_valign(Gtk.Align.CENTER)
        text_box.set_hexpand(True)

        title = Gtk.Label(label=_("DaVinci Resolve Installer"))
        title.add_css_class("title-3")
        title.set_halign(Gtk.Align.START)
        text_box.append(title)

        subtitle = Gtk.Label(
            label=_("Supports both DaVinci Resolve and DaVinci Resolve Studio")
        )
        subtitle.add_css_class("dim-label")
        subtitle.set_halign(Gtk.Align.START)
        subtitle.set_wrap(True)
        text_box.append(subtitle)

        header.append(text_box)

        self.action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.action_box.set_valign(Gtk.Align.CENTER)
        header.append(self.action_box)

        self.append(header)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

    def _build_content_stack(self):
        self.content_stack = Gtk.Stack()
        self.content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.content_stack.set_hexpand(True)
        self.content_stack.set_vexpand(True)

        self._build_carousel()
        self._build_progress()

        self.append(self.content_stack)

    def _build_carousel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.set_valign(Gtk.Align.FILL)
        box.set_vexpand(True)
        box.set_margin_top(24)
        box.set_margin_bottom(16)

        self.btn_prev = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self.btn_prev.add_css_class("flat")
        self.btn_prev.add_css_class("circular")
        self.btn_prev.set_valign(Gtk.Align.CENTER)
        self.btn_prev.connect("clicked", lambda _b: self._navigate_screenshot(-1))
        box.append(self.btn_prev)

        bg = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bg.add_css_class("screenshot-bg-davinci")
        bg.set_hexpand(True)
        bg.set_vexpand(True)
        bg.set_valign(Gtk.Align.FILL)

        self.screenshot_picture = Gtk.Picture()
        self.screenshot_picture.set_can_shrink(True)
        try:
            self.screenshot_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        except AttributeError:
            pass
        self.screenshot_picture.set_hexpand(True)
        self.screenshot_picture.set_vexpand(True)
        bg.append(self.screenshot_picture)

        box.append(bg)

        self.btn_next = Gtk.Button.new_from_icon_name("go-next-symbolic")
        self.btn_next.add_css_class("flat")
        self.btn_next.add_css_class("circular")
        self.btn_next.set_valign(Gtk.Align.CENTER)
        self.btn_next.connect("clicked", lambda _b: self._navigate_screenshot(1))
        box.append(self.btn_next)

        self._show_screenshot(0)
        self.content_stack.add_named(box, "carousel")

    def _build_progress(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        box.set_vexpand(True)
        box.set_hexpand(True)
        box.set_margin_start(60)
        box.set_margin_end(60)
        box.set_margin_top(40)
        box.set_margin_bottom(40)

        self.step_label = Gtk.Label()
        self.step_label.add_css_class("title-4")
        box.append(self.step_label)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_hexpand(True)
        box.append(self.progress_bar)

        self.warning_label = Gtk.Label(
            label=_("Installation in progress. Do NOT close the app.")
        )
        self.warning_label.add_css_class("title-3")
        box.append(self.warning_label)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        box.append(spacer)

        note = Gtk.Label()
        note.set_markup(
            _("This may take a while depending on your internet speed and hardware.")
        )
        note.set_justify(Gtk.Justification.CENTER)
        note.set_wrap(True)
        note.add_css_class("dim-label")
        box.append(note)

        self.content_stack.add_named(box, "progress")

    # ── Screenshot carousel ─────────────────────────────────────────

    def _show_screenshot(self, index):
        if not self.screenshots:
            self.btn_prev.set_visible(False)
            self.btn_next.set_visible(False)
            return
        self.current_screenshot_idx = index % len(self.screenshots)
        self.screenshot_picture.set_filename(
            self.screenshots[self.current_screenshot_idx]
        )
        has_many = len(self.screenshots) > 1
        self.btn_prev.set_sensitive(has_many)
        self.btn_next.set_sensitive(has_many)

    def _navigate_screenshot(self, delta):
        self._show_screenshot(self.current_screenshot_idx + delta)

    # ── State management ────────────────────────────────────────────

    def _clear_actions(self):
        child = self.action_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.action_box.remove(child)
            child = nxt

    def _set_state_pre_install(self):
        self._clear_actions()

        btn = Gtk.Button(label=_("Select Installer File"))
        btn.add_css_class("suggested-action")
        btn.connect("clicked", self._on_select_run)
        self.action_box.append(btn)

        self.content_stack.set_visible_child_name("carousel")

    def _set_state_installing(self):
        self._clear_actions()
        btn = Gtk.Button(label=_("Installing..."))
        btn.set_sensitive(False)
        self.action_box.append(btn)
        self.content_stack.set_visible_child_name("progress")

    def _set_state_post_install(self):
        self._clear_actions()

        self.btn_remove = Gtk.Button(label=_("Remove"))
        self.btn_remove.add_css_class("destructive-action")
        self.btn_remove.connect("clicked", self._on_remove)
        self.action_box.append(self.btn_remove)

        self.btn_launch = Gtk.Button(label=_("Launch"))
        self.btn_launch.add_css_class("suggested-action")
        self.btn_launch.connect("clicked", self._on_launch)
        self.action_box.append(self.btn_launch)

        self.content_stack.set_visible_child_name("carousel")

    # ── Installation detection ──────────────────────────────────────

    @staticmethod
    def _is_installed():
        return os.path.isfile(RESOLVE_BIN)

    # ── Action handlers ─────────────────────────────────────────────

    def _on_select_run(self, _btn):
        parent = self.get_root()
        dlg = Gtk.FileChooserDialog(
            title=_("Select DaVinci Resolve .run file"),
            transient_for=parent,
            modal=True,
            action=Gtk.FileChooserAction.OPEN,
        )
        dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dlg.add_button(_("Open"), Gtk.ResponseType.OK)

        flt = Gtk.FileFilter()
        flt.set_name(_("DaVinci Resolve Installer (*.run)"))
        flt.add_pattern("*.run")
        dlg.add_filter(flt)

        def on_resp(d, r):
            if r == Gtk.ResponseType.OK:
                f = d.get_file()
                if f:
                    self.pending_run_file_path = f.get_path()
                    self._prompt_password()
            d.destroy()

        dlg.connect("response", on_resp)
        dlg.present()

    def _on_remove(self, _btn):
        dlg = Adw.MessageDialog(
            heading=_("Are you sure?"),
            body=_("This will remove DaVinci Resolve from your system."),
            transient_for=self.get_root() or self.window,
        )
        dlg.add_response("cancel", _("Cancel"))
        dlg.add_response("remove", _("Remove"))
        dlg.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_resp(d, r):
            d.close()
            if r == "remove":
                self._prompt_password_for_removal()

        dlg.connect("response", on_resp)
        try:
            translate_dialog(dlg)
        except NameError:
            pass
        dlg.present()

    @staticmethod
    def _is_kde_plasma():
        return os.environ.get("XDG_CURRENT_DESKTOP", "").lower().find("kde") != -1

    def _on_launch(self, _btn):
        self._set_buttons_launching()

        def _wait_for_exit():
            if self._is_kde_plasma():
                try:
                    subprocess.run(
                        ["qdbus", "org.kde.kded6", "/kded",
                         "org.kde.kded6.unloadModule", "appmenu"],
                        check=True, start_new_session=True,
                    )
                    proc = subprocess.Popen(
                        [RESOLVE_BIN], start_new_session=True,
                    )
                    proc.wait()
                    import time; time.sleep(2)
                    subprocess.run(
                        ["qdbus", "org.kde.kded6", "/kded",
                         "org.kde.kded6.loadModule", "appmenu"],
                        start_new_session=True,
                    )
                    GLib.idle_add(self._set_buttons_idle)
                    return
                except Exception:
                    pass

            proc = subprocess.Popen(
                [RESOLVE_BIN], start_new_session=True,
            )
            proc.wait()
            GLib.idle_add(self._set_buttons_idle)

        threading.Thread(target=_wait_for_exit, daemon=True).start()

    def _set_buttons_launching(self):
        self.btn_launch.set_label(_("Launching..."))
        self.btn_launch.set_sensitive(False)
        self.btn_remove.set_sensitive(False)

    def _set_buttons_idle(self):
        self.btn_launch.set_label(_("Launch"))
        self.btn_launch.set_sensitive(True)
        self.btn_remove.set_sensitive(True)

    # ── Remove helper ───────────────────────────────────────────────
    def _prompt_password_for_removal(self):
        dlg = Adw.MessageDialog(
            heading=_("Authentication Required"),
            body=_("Please enter your password to proceed with the removal."),
            transient_for=self.get_root() or self.window,
        )
        dlg.add_response("cancel", _("Cancel"))
        dlg.add_response("unlock", _("Unlock"))
        dlg.set_response_appearance("unlock", Adw.ResponseAppearance.SUGGESTED)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        entry = Gtk.PasswordEntry()
        entry.set_property("placeholder-text", _("Password"))
        box.append(entry)
        dlg.set_extra_child(box)

        def on_resp(d, r):
            d.close()
            if r == "unlock":
                pwd = entry.get_text()
                if pwd:
                    try:
                        if sudo_manager.validate_password(pwd):
                            sudo_manager.set_password(pwd)
                            self._perform_removal()
                        else:
                            self._show_auth_error()
                    except NameError:
                        self._perform_removal()
            else:
                self._set_state_post_install()

        dlg.connect("response", on_resp)
        entry.connect("activate", lambda _w: dlg.response("unlock"))
        try:
            translate_dialog(dlg)
        except NameError:
            pass
        dlg.present()
    def _perform_removal(self):
        self._clear_actions()
        btn = Gtk.Button(label=_("Removing..."))
        btn.set_sensitive(False)
        self.action_box.append(btn)

        def _remove():
            try:
                sudo_manager.start_privileged_session()
                env = sudo_manager.get_env()
                sudo_wrap = sudo_manager.wrapper_path

                # Try removing both package variants
                subprocess.run(
                    f"{sudo_wrap} pacman -Rns --noconfirm davinci-resolve davinci-resolve-studio 2>/dev/null; true",
                    shell=True, env=env,
                )
            except NameError:
                subprocess.run(
                    "sudo pacman -Rns --noconfirm davinci-resolve davinci-resolve-studio 2>/dev/null; true",
                    shell=True,
                )
            finally:
                try:
                    sudo_manager.stop_privileged_session()
                    sudo_manager.forget_password()
                except NameError:
                    pass

            GLib.idle_add(self._set_state_pre_install)

        threading.Thread(target=_remove, daemon=True).start()

    # ── Password prompt ─────────────────────────────────────────────

    def _prompt_password(self):
        dlg = Adw.MessageDialog(
            heading=_("Authentication Required"),
            body=_("Please enter your password to proceed with the installation."),
            transient_for=self.get_root() or self.window,
        )
        dlg.add_response("cancel", _("Cancel"))
        dlg.add_response("unlock", _("Unlock"))
        dlg.set_response_appearance("unlock", Adw.ResponseAppearance.SUGGESTED)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        entry = Gtk.PasswordEntry()
        entry.set_property("placeholder-text", _("Password"))
        box.append(entry)
        dlg.set_extra_child(box)

        def on_resp(d, r):
            d.close()
            if r == "unlock":
                pwd = entry.get_text()
                if pwd:
                    try:
                        if sudo_manager.validate_password(pwd):
                            sudo_manager.set_password(pwd)
                            self.user_password = pwd
                            self._attempt_installation()
                        else:
                            self._show_auth_error()
                    except NameError:
                        self.user_password = pwd
                        self._attempt_installation()

        dlg.connect("response", on_resp)
        entry.connect("activate", lambda _w: dlg.response("unlock"))
        try:
            translate_dialog(dlg)
        except NameError:
            pass
        dlg.present()

    def _show_auth_error(self):
        dlg = Adw.MessageDialog(
            heading=_("Authentication Failed"),
            body=_("Incorrect password."),
            transient_for=self.get_root() or self.window,
        )
        dlg.add_response("ok", _("OK"))
        try:
            translate_dialog(dlg)
        except NameError:
            pass
        dlg.present()

    # ── GPU / OpenCL detection ──────────────────────────────────────

    def _detect_opencl_package(self):
        try:
            lspci = subprocess.run(
                ["lspci", "-nn"],
                capture_output=True, text=True, timeout=5,
            )
            output = lspci.stdout.lower()
            # Check VGA and 3D controller lines for GPU vendor
            has_nvidia = bool(re.search(r"(?:vga|3d).*\bnvidia\b", output))
            has_amd = bool(re.search(r"(?:vga|3d).*\b(?:amd|ati|radeon)\b", output))
            if has_nvidia and not has_amd:
                return "opencl-nvidia"
            elif has_amd and not has_nvidia:
                return "opencl-amd"
            elif has_nvidia and has_amd:
                # Hybrid GPU — install both
                return "opencl-amd opencl-nvidia"
        except Exception:
            pass
        # Fallback: check what's already installed
        for pkg in ("opencl-amd", "opencl-mesa", "opencl-nvidia", "intel-compute-runtime", "rocm-opencl-runtime"):
            r = subprocess.run(
                ["pacman", "-Qq", pkg],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if r.returncode == 0:
                return pkg
        return "opencl-mesa"

    _OPENCL_AMD_COMMIT = "42c9eb7"

    def _install_opencl_amd(self, sudo_wrap, env, on_line=None):
        """Build and install opencl-amd from AUR at a known-good commit."""
        # Skip if already installed at the pinned version
        r = subprocess.run(
            ["pacman", "-Qq", "opencl-amd"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if r.returncode == 0:
            return
        tmpdir = tempfile.mkdtemp(prefix="opencl-amd-")
        try:
            clone_cmd = (
                f"git clone https://aur.archlinux.org/opencl-amd.git {shlex.quote(tmpdir)}/opencl-amd "
                f"&& cd {shlex.quote(tmpdir)}/opencl-amd "
                f"&& git checkout {self._OPENCL_AMD_COMMIT} "
                f"&& PACMAN_AUTH='{sudo_wrap}' makepkg -si --noconfirm --needed"
            )
            self._run_cmd(clone_cmd, env=env, on_line=on_line)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ── Build environment ───────────────────────────────────────────

    def _prepare_build_environment(self, run_file_path, is_studio):
        original_dir = os.path.dirname(run_file_path)
        self.tmp_build_dir = os.path.join(original_dir, "davinci_tmp")
        os.makedirs(self.tmp_build_dir, exist_ok=True)
        self.original_run_file_path = run_file_path

        if is_studio:
            source_dir = "/usr/share/linexin/davincistudio"
            install_file_name = "davinci-resolve-studio.install"
        else:
            source_dir = "/usr/share/linexin/davinci"
            install_file_name = "davinci-resolve.install"

        source_pkgbuild = os.path.join(source_dir, "PKGBUILD")
        source_panels_script = os.path.join(source_dir, "davinci-control-panels-setup.sh")
        source_install_file = os.path.join(source_dir, install_file_name)

        for f in [source_pkgbuild, source_panels_script, source_install_file]:
            if not os.path.exists(f):
                raise FileNotFoundError(_("Required file not found at {}").format(f))

        src_dir = os.path.join(self.tmp_build_dir, "src")
        os.makedirs(src_dir, exist_ok=True)

        shutil.copy2(source_pkgbuild, os.path.join(self.tmp_build_dir, "PKGBUILD"))
        shutil.copy2(source_install_file, os.path.join(self.tmp_build_dir, install_file_name))
        shutil.copy2(source_panels_script, os.path.join(self.tmp_build_dir, "davinci-control-panels-setup.sh"))

        dest_pkgbuild = os.path.join(self.tmp_build_dir, "PKGBUILD")
        filename = os.path.basename(run_file_path)
        match = re.search(r"DaVinci_Resolve(?:_Studio)?_([\d\.]+)_Linux\.run", filename)
        if not match:
            raise ValueError(_("Could not extract version number from filename: {}").format(filename))

        new_version = match.group(1)
        opencl_pkg = self._detect_opencl_package()
        opencl_deps = " ".join(f"'{p}'" for p in opencl_pkg.split())
        with open(dest_pkgbuild, "r") as f:
            content = f.read()
        content = re.sub(r"(?m)^(pkgver=).*", f"pkgver={new_version}", content)
        content = content.replace("'opencl-driver'", opencl_deps)
        with open(dest_pkgbuild, "w") as f:
            f.write(content)

        shutil.move(run_file_path, os.path.join(src_dir, filename))

    def _cleanup_build_environment(self):
        if not self.tmp_build_dir or not self.original_run_file_path:
            return
        try:
            tmp_run = os.path.join(
                self.tmp_build_dir, "src", os.path.basename(self.original_run_file_path)
            )
            if os.path.exists(tmp_run):
                shutil.move(tmp_run, self.original_run_file_path)
            if os.path.exists(self.tmp_build_dir):
                shutil.rmtree(self.tmp_build_dir)
        except Exception:
            pass
        finally:
            self.tmp_build_dir = None
            self.original_run_file_path = None

    def _configure_pacman_ignore(self, app_package_name, extra_ignore=None):
        all_packages = [app_package_name] if app_package_name else []
        if extra_ignore:
            for p in extra_ignore:
                if p not in all_packages:
                    all_packages.append(p)
        pkg_list_str = " ".join(all_packages)
        script_content = r"""
import sys, re, os
conf_path = '/etc/pacman.conf'
extra_pkgs = '%s'.split()
try:
    with open(conf_path, 'r') as f:
        lines = f.readlines()
    new_lines = []
    ignore_pkg_found = False
    packages = ['libc++', 'libc++abi'] + extra_pkgs
    for line in lines:
        if re.match(r'^\s*#?\s*IgnorePkg\s*=', line):
            ignore_pkg_found = True
            content = line.strip().lstrip('#').strip()
            existing_pkgs = []
            if '=' in content:
                parts = content.split('=', 1)
                if len(parts) > 1:
                    existing_pkgs = parts[1].strip().split()
            for pkg in packages:
                if pkg not in existing_pkgs:
                    existing_pkgs.append(pkg)
            new_lines.append(f"IgnorePkg = {' '.join(existing_pkgs)}\n")
        else:
            new_lines.append(line)
    if not ignore_pkg_found:
        final_lines = []
        inserted = False
        for line in new_lines:
            final_lines.append(line)
            if line.strip() == '[options]' and not inserted:
                final_lines.append(f"IgnorePkg = {' '.join(packages)}\n")
                inserted = True
        if not inserted:
            final_lines.append(f"IgnorePkg = {' '.join(packages)}\n")
        new_lines = final_lines
    with open(conf_path, 'w') as f:
        f.writelines(new_lines)
except Exception as e:
    print(f"Error updating pacman.conf: {e}")
    sys.exit(1)
""" % (pkg_list_str)
        script_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as tf:
                tf.write(script_content)
                script_path = tf.name
            env = sudo_manager.get_env()
            sudo_manager.run_privileged(["python3", script_path], check=True, env=env)
        except Exception:
            pass
        finally:
            if script_path and os.path.exists(script_path):
                os.remove(script_path)

    # ── Installation flow ───────────────────────────────────────────

    def _attempt_installation(self):
        if not hasattr(self, 'pending_run_file_path') or not self.pending_run_file_path:
            return

        run_file_path = self.pending_run_file_path
        filename = os.path.basename(run_file_path)
        is_studio = "_Studio_" in filename
        self.current_product = "DaVinci Resolve Studio" if is_studio else "DaVinci Resolve"

        try:
            self._prepare_build_environment(run_file_path, is_studio)
        except Exception as e:
            self._show_install_error(str(e))
            self._cleanup_build_environment()
            return

        self.install_started = True
        self.error_message = None
        self.progress_data = ""
        self.total_steps = 3

        self._set_state_installing()
        self._update_step(0, _("Preparing..."))

        threading.Thread(target=self._run_install, daemon=True).start()

    def _update_step(self, step, label):
        self.step_label.set_label(label)
        self.progress_bar.set_fraction(step / self.total_steps)

    def _step_on_main(self, step, label):
        GLib.idle_add(self._update_step, step, label)

    def _run_install(self):
        try:
            sudo_manager.start_privileged_session()
        except NameError:
            pass

        step = 0
        try:
            try:
                env = sudo_manager.get_env()
                sudo_wrap = sudo_manager.wrapper_path
            except NameError:
                env = os.environ.copy()
                sudo_wrap = "sudo"

            # ── Step 1: Install dependencies ──
            step += 1
            self._step_on_main(
                step, _("Step {}: Installing dependencies...").format(step)
            )

            # AUR-only deps must be installed first so pacman can resolve them later
            aur_deps = "qt5-location"
            opencl_pkg = self._detect_opencl_package()

            # opencl-amd needs to be built from AUR at a pinned commit;
            # install it separately and exclude from the regular dep list
            needs_opencl_amd = "opencl-amd" in opencl_pkg
            regular_opencl = opencl_pkg.replace("opencl-amd", "").strip()

            dep_list = (
                "glu gtk2 libpng12 fuse2 qt5-x11extras qt5-svg "
                "qt5-webengine qt5-websockets qt5-quickcontrols2 qt5-multimedia libxcrypt-compat "
                "xmlsec java-runtime ffmpeg4.4 gst-plugins-bad-libs python-numpy tbb apr-util luajit"
            )
            if regular_opencl:
                dep_list = f"{regular_opencl} {dep_list}"
            davinci_deps = dep_list
            aur_cmd = f"paru -Sy --noconfirm --needed --skipreview --removemake {aur_deps} --sudo '{sudo_wrap}'"
            paru_cmd = f"paru -Sy --noconfirm --needed --skipreview --removemake {davinci_deps} --sudo '{sudo_wrap}'"
            libs_cmd = f"{sudo_wrap} pacman -Sy --noconfirm --overwrite '*' linexin-repo/libc++ linexin-repo/libc++abi"

            _building_re = re.compile(r"^==> Making package:\s+(\S+)")
            _installing_re = re.compile(r"^installing\s+(\S+)")

            def _on_dep_line(line):
                m = _building_re.match(line) or _installing_re.match(line)
                if m:
                    pkg = m.group(1).rstrip(".")
                    GLib.idle_add(
                        self.step_label.set_label,
                        _("Step {}: Installing dependencies...").format(step) + f"  ({pkg})",
                    )

            self._run_cmd(f"{aur_cmd} && {paru_cmd} && {libs_cmd}", env=env, on_line=_on_dep_line)

            if needs_opencl_amd:
                self._step_on_main(
                    step, _("Step {}: Installing dependencies...").format(step) + "  (opencl-amd)",
                )
                self._install_opencl_amd(sudo_wrap, env, on_line=_on_dep_line)

            # ── Step 2: Building and installing ──
            step += 1
            self._step_on_main(
                step, _("Step {}: Installing DaVinci Resolve...").format(step)
            )

            quoted_tmp = shlex.quote(self.tmp_build_dir)
            build_cmd = f"cd {quoted_tmp} && export PACMAN_AUTH='{sudo_wrap}' && makepkg -si --noconfirm --skipinteg --needed"
            self._run_cmd(build_cmd, env=env)

            # ── Step 3: Finishing up ──
            step += 1
            self._step_on_main(
                step, _("Step {}: Finishing up...").format(step)
            )

            fix_cmd = f"{sudo_wrap} chown -R $USER:$(id -gn) /opt/resolve"
            self._run_cmd(fix_cmd, env=env)

            pkg_name = "davinci-resolve-studio" if "Studio" in self.current_product else "davinci-resolve"
            try:
                ignore_pkgs = [pkg_name]
                if needs_opencl_amd:
                    ignore_pkgs.append("opencl-amd")
                self._configure_pacman_ignore(pkg_name, extra_ignore=ignore_pkgs)
            except Exception:
                pass

        except Exception as e:
            self.error_message = str(e)
            print(f"Installation error: {e}", flush=True)

        self._cleanup_build_environment()
        GLib.idle_add(self._finish_install)

    def _run_cmd(self, command, env=None, on_line=None):
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        for line in iter(proc.stdout.readline, ""):
            if line:
                self.progress_data += line
                print(line, end="", flush=True)
                if on_line:
                    on_line(line)
        proc.stdout.close()
        rc = proc.wait()
        if rc != 0:
            # Extract last meaningful lines from output for the error message
            tail = [l for l in self.progress_data.strip().splitlines() if l.strip()][-15:]
            detail = "\n".join(tail) if tail else _("No output captured.")
            raise RuntimeError(detail)

    def _finish_install(self):
        self.install_started = False
        try:
            sudo_manager.stop_privileged_session()
            sudo_manager.forget_password()
        except NameError:
            pass
        self.user_password = None

        if self.error_message:
            self._show_install_error(self.error_message)
            self._set_state_pre_install()
        else:
            self._set_state_post_install()

        return False

    def _show_install_error(self, message):
        dlg = Adw.MessageDialog(
            heading=_("Installation failed"),
            body=message,
            transient_for=self.get_root() or self.window,
        )
        dlg.add_response("ok", _("OK"))
        try:
            translate_dialog(dlg)
        except NameError:
            pass
        dlg.present()
