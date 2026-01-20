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
import tempfile
import atexit

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

# --- Localization Setup ---
APP_NAME = "davinci-installer"
LOCALE_DIR = os.path.abspath("./locale")

# Set up the locale environment
locale.setlocale(locale.LC_ALL, '')
locale.bindtextdomain(APP_NAME, LOCALE_DIR)
gettext.bindtextdomain(APP_NAME, LOCALE_DIR)
gettext.textdomain(APP_NAME)
_ = gettext.gettext
# --------------------------

class DaVinciInstallerWidget(Gtk.Box):
    def __init__(self, hide_sidebar=False, window=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        
        # Required: Widget display name
        self.widgetname = "DaVinci Installer"
        
        # Optional: Widget icon
        self.widgeticon = "/usr/share/icons/github.petexy.davinciinstaller.png"
        
        # Widget content
        self.set_margin_top(12)
        self.set_margin_bottom(50)
        self.set_margin_start(12)
        self.set_margin_end(12)
        
        # Initialize state variables
        self.progress_visible = False
        self.progress_data = ""
        self.install_started = False
        self.error_message = None
        self.tmp_build_dir = None
        self.original_run_file_path = None
        
        # Sudo wrapper state
        self.user_password = None
        self._askpass_tf = tempfile.NamedTemporaryFile(delete=False, prefix="linexin-askpass-")
        self.askpass_script = self._askpass_tf.name
        self._askpass_tf.close()
        self._sudo_tf = tempfile.NamedTemporaryFile(delete=False, prefix="linexin-sudo-")
        self.sudo_wrapper = self._sudo_tf.name
        self._sudo_tf.close()
        atexit.register(self.cleanup_temp_files)
        
        # Create main content stack
        self.content_stack = Gtk.Stack()
        self.content_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_UP_DOWN)
        self.content_stack.set_hexpand(True)
        self.content_stack.set_vexpand(True)
        self.append(self.content_stack)
        
        # Setup different views
        self.setup_welcome_view()
        self.setup_info_view()
        self.setup_progress_view()
        
        # Controls section
        self.setup_controls()
        
        # Set initial view
        self.content_stack.set_visible_child_name("welcome_view")

        self.window = window
        self.hide_sidebar = hide_sidebar

        if not self.hide_sidebar:
            pass
        else:
            # Single widget mode
            GLib.idle_add(self.resize_window_deferred)
    
    
    def cleanup_temp_files(self):
        try:
            if os.path.exists(self.askpass_script):
                os.remove(self.askpass_script)
            if os.path.exists(self.sudo_wrapper):
                os.remove(self.sudo_wrapper)
        except:
            pass

    def setup_sudo_env(self):
        """Create helper scripts for non-interactive sudo"""
        with open(self.askpass_script, "w") as f:
            f.write("#!/bin/sh\necho \"$LINEXIN_SUDO_PW\"\n")
        os.chmod(self.askpass_script, 0o700)
        
        with open(self.sudo_wrapper, "w") as f:
            f.write(f"#!/bin/sh\nexport SUDO_ASKPASS='{self.askpass_script}'\nexec sudo -A \"$@\"\n")
        os.chmod(self.sudo_wrapper, 0o700)

    def prompt_for_password(self):
        """Prompt user for sudo password using Adw.MessageDialog"""
        root = self.get_root()
        if not root:
            root = self.window
            
        dialog = Adw.MessageDialog(
            heading=_("Authentication Required"),
            body=_("Please enter your password to proceed with the installation."),
            transient_for=root
        )
        
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("unlock", _("Unlock"))
        dialog.set_response_appearance("unlock", Adw.ResponseAppearance.SUGGESTED)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        
        entry = Gtk.PasswordEntry()
        entry.set_property("placeholder-text", _("Password"))
        box.append(entry)
        
        dialog.set_extra_child(box)
        
        def on_response(dialog, response):
            if response == "unlock":
                pwd = entry.get_text()
                if pwd:
                    self.user_password = pwd
                    # Resume installation flow
                    self.attempt_installation()
            dialog.close()
            
        dialog.connect("response", on_response)
        
        def on_entry_activate(widget):
            dialog.response("unlock")
            
        entry.connect("activate", on_entry_activate)
        
        dialog.present()

    def validate_password(self):
        """Validate the sudo password using sudo -S"""
        if not self.user_password:
            return False
            
        try:
            subprocess.run(['sudo', '-k'], check=False)
            
            result = subprocess.run(
                ['sudo', '-S', '-v'],
                input=(self.user_password + '\n'),
                capture_output=True,
                text=True,
                env={'LC_ALL': 'C'}
            )
            
            if result.returncode == 0:
                return True
            else:
                print(f"Password validation failed. Return code: {result.returncode}")
                return False
        except Exception as e:
            print(f"Validation exception: {e}")
            return False

    def resize_window_deferred(self):
        """Called after widget initialization to resize window safely"""
        if self.window:
            try:
                self.window.set_default_size(800, 600)
                print("Window default size set to 1400x800")
            except Exception as e:
                print(f"Failed to resize window: {e}")
        return False

    def setup_welcome_view(self):
        """Setup the welcome view with icon and description"""
        welcome_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        welcome_box.set_valign(Gtk.Align.CENTER)
        welcome_box.set_halign(Gtk.Align.CENTER)
        
        # Welcome icon
        welcome_image = Gtk.Image()
        if os.path.exists("/usr/share/icons/github.petexy.davinciinstaller.png"):
            welcome_image.set_from_file("/usr/share/icons/github.petexy.davinciinstaller.png")
        else:
            welcome_image.set_from_icon_name("package-x-generic")
        welcome_image.set_pixel_size(64)
        welcome_box.append(welcome_image)
        
        # Title
        title = Gtk.Label(label=_("DaVinci Resolve Installer"))
        title.add_css_class("title-2")
        welcome_box.append(title)
        
        # Description
        description = Gtk.Label()
        description.set_markup(_("Install DaVinci Resolve from .run file\n\nSupports both DaVinci Resolve and DaVinci Resolve Studio"))
        description.set_justify(Gtk.Justification.CENTER)
        description.add_css_class("dim-label")
        welcome_box.append(description)
        
        self.content_stack.add_named(welcome_box, "welcome_view")
    
    def setup_info_view(self):
        """Setup the info view for status messages"""
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        info_box.set_valign(Gtk.Align.CENTER)
        info_box.set_halign(Gtk.Align.CENTER)
        
        # Status images
        self.fail_image = Gtk.Image()
        self.fail_image.set_from_icon_name("dialog-error")
        self.fail_image.set_pixel_size(48)
        self.fail_image.set_visible(False)
        
        self.success_image = Gtk.Image()
        self.success_image.set_from_icon_name("emblem-ok")
        self.success_image.set_pixel_size(48)
        self.success_image.set_visible(False)
        
        info_box.append(self.fail_image)
        info_box.append(self.success_image)
        
        # Status label
        self.info_label = Gtk.Label()
        self.info_label.set_wrap(True)
        self.info_label.set_justify(Gtk.Justification.CENTER)
        info_box.append(self.info_label)
        
        self.content_stack.add_named(info_box, "info_view")
    
    def setup_progress_view(self):
        """Setup the progress view with terminal output"""
        self.output_buffer = Gtk.TextBuffer()
        self.output_textview = Gtk.TextView.new_with_buffer(self.output_buffer)
        self.output_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.output_textview.set_editable(False)
        self.output_textview.set_cursor_visible(False)
        self.output_textview.set_monospace(True)
        self.output_textview.set_left_margin(10)
        self.output_textview.set_right_margin(10)
        self.output_textview.set_top_margin(5)
        self.output_textview.set_bottom_margin(5)
        
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_child(self.output_textview)
        scrolled_window.set_min_content_height(200)
        
        output_frame = Gtk.Frame()
        output_frame.set_child(scrolled_window)
        self.content_stack.add_named(output_frame, "progress_view")
    
    def setup_controls(self):
        """Setup control buttons"""
        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        controls_box.set_halign(Gtk.Align.CENTER)
        
        self.btn_install = Gtk.Button(label=_("Select Installer File"))
        self.btn_install.add_css_class("suggested-action")
        self.btn_install.add_css_class("buttons_all")
        self.btn_install.connect("clicked", self.on_install_clicked)
        
        self.btn_toggle_progress = Gtk.Button(label=_("Show Progress"))
        self.btn_toggle_progress.set_sensitive(False)
        self.btn_toggle_progress.set_visible(False)
        self.btn_toggle_progress.add_css_class("buttons_all")
        self.btn_toggle_progress.connect("clicked", self.on_toggle_progress_clicked)
        
        controls_box.append(self.btn_install)
        controls_box.append(self.btn_toggle_progress)
        
        self.append(controls_box)
    
    def on_install_clicked(self, button):
        """Handle install button click - opens file chooser"""
        self.create_file_chooser()
    
    def create_file_chooser(self):
        """Creates and shows a file chooser dialog"""
        title = _("Select DaVinci Resolve .run file")
        
        # Get the toplevel window to use as parent
        parent_window = self.get_root()
        
        file_chooser = Gtk.FileChooserDialog(
            title=title,
            transient_for=parent_window,
            modal=True,
            action=Gtk.FileChooserAction.OPEN
        )
        
        file_chooser.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        file_chooser.add_button(_("Open"), Gtk.ResponseType.OK)
        
        file_filter = Gtk.FileFilter()
        file_filter.set_name(_("DaVinci Resolve Installer (*.run)"))
        file_filter.add_pattern("*.run")
        file_chooser.add_filter(file_filter)
        
        file_chooser.connect("response", self.on_file_chooser_response)
        file_chooser.present()
    
    def prepare_build_environment(self, run_file_path, is_studio):
        """Creates a temporary build dir, copies files, and moves the installer"""
        original_dir = os.path.dirname(run_file_path)
        self.tmp_build_dir = os.path.join(original_dir, "davinci_tmp")
        os.makedirs(self.tmp_build_dir, exist_ok=True)
        
        self.original_run_file_path = run_file_path
        dest_dir = self.tmp_build_dir
        
        # Define source paths based on whether it's a Studio version
        if is_studio:
            source_dir = "/usr/share/linexin/davincistudio"
            install_file_name = "davinci-resolve-studio.install"
        else:
            source_dir = "/usr/share/linexin/davinci"
            install_file_name = "davinci-resolve.install"
        
        # Define all source files
        source_pkgbuild = os.path.join(source_dir, "PKGBUILD")
        source_panels_script = os.path.join(source_dir, "davinci-control-panels-setup.sh")
        source_install_file = os.path.join(source_dir, install_file_name)
        
        # Check if all source files exist
        for f in [source_pkgbuild, source_panels_script, source_install_file]:
            if not os.path.exists(f):
                raise FileNotFoundError(_("Required file not found at {}").format(f))
        
        # Create 'src' directory inside the tmp dir
        src_dir = os.path.join(self.tmp_build_dir, "src")
        os.makedirs(src_dir, exist_ok=True)
        
        # Copy PKGBUILD, .install file, and panels script to the root of tmp_dir
        shutil.copy2(source_pkgbuild, os.path.join(dest_dir, "PKGBUILD"))
        shutil.copy2(source_install_file, os.path.join(dest_dir, install_file_name))
        shutil.copy2(source_panels_script, os.path.join(dest_dir, "davinci-control-panels-setup.sh"))
        
        # Update the pkgver in the copied PKGBUILD
        dest_pkgbuild = os.path.join(dest_dir, "PKGBUILD")
        filename = os.path.basename(run_file_path)
        match = re.search(r"DaVinci_Resolve(?:_Studio)?_([\d\.]+)_Linux\.run", filename)
        if not match:
            raise ValueError(_("Could not extract version number from filename: {}").format(filename))
        new_version = match.group(1)
        
        with open(dest_pkgbuild, "r") as f:
            lines = f.readlines()
        new_lines = [f"pkgver={new_version}\n" if l.strip().startswith("pkgver=") else l for l in lines]
        with open(dest_pkgbuild, "w") as f:
            f.writelines(new_lines)
        
        # Move the .run file from its original location into 'src'
        shutil.move(run_file_path, os.path.join(src_dir, filename))
    
    def on_file_chooser_response(self, dialog, response_id):
        """Handles file selection, calls attempt_installation to proceed"""
        if response_id == Gtk.ResponseType.OK:
            file = dialog.get_file()
            if file:
                self.pending_run_file_path = file.get_path()
                self.attempt_installation()
            else:
                self.show_error_message(_("No file selected. Installation cancelled."))
        else:
            self.show_error_message(_("Installation cancelled."))
        
        dialog.destroy()

    def attempt_installation(self):
        """Check auth and proceed with installation"""
        if not hasattr(self, 'pending_run_file_path') or not self.pending_run_file_path:
            return

        # 1. Check for password
        if not self.user_password:
            self.prompt_for_password()
            return
        
        # 2. Validate password
        self.setup_sudo_env()
        if not self.validate_password():
            self.user_password = None
            
            root = self.get_root() or self.window
            dialog = Adw.MessageDialog(
                heading=_("Authentication Failed"),
                body=_("The password you entered is incorrect. Please try again."),
                transient_for=root
            )
            dialog.add_response("ok", _("OK"))
            dialog.set_response_appearance("ok", Adw.ResponseAppearance.DEFAULT)
            dialog.connect("response", lambda d, r: d.close())
            dialog.present()
            return

        # 3. Proceed with install
        run_file_path = self.pending_run_file_path
        filename = os.path.basename(run_file_path)
        
        # Determine product based on filename
        is_studio = "_Studio_" in filename
        product_name = "DaVinci Resolve Studio" if is_studio else "DaVinci Resolve"
        
        try:
            # Prepare the entire build environment in a temporary directory
            self.prepare_build_environment(run_file_path, is_studio)
            
            # Define the new installation command
            # 1) Install dependencies from linexin-repo
            # 2) Build package using sudo wrapper for pacman authentication
            quoted_tmp_dir = shlex.quote(self.tmp_build_dir)
            
            install_deps_cmd = f"{self.sudo_wrapper} pacman -Sy --noconfirm --overwrite '*' linexin-repo/libc++ linexin-repo/libc++abi"
            
            build_cmd = f"cd {quoted_tmp_dir} && export PACMAN_AUTH='{self.sudo_wrapper}' && makepkg -si --noconfirm --skipinteg"
            
            full_command = f"{install_deps_cmd} && {build_cmd}"
            
            # Start the installation process
            self.begin_install(full_command, product_name)
        
        except Exception as e:
            self.show_error_message(_("Failed to prepare for installation: {}").format(e))
            self.cleanup_build_environment()
        try:
            # Add the new method before cleanup_build_environment
            pass 
        except:
             pass
    
    def configure_pacman_ignore(self, app_package_name):
        """Add libc++, libc++abi and the app package to IgnorePkg in pacman.conf"""
        script_content = r"""
import sys
import re
import os

conf_path = '/etc/pacman.conf'
app_package = '%s'

try:
    with open(conf_path, 'r') as f:
        lines = f.readlines()

    new_lines = []
    ignore_pkg_found = False
    packages = ['libc++', 'libc++abi']
    if app_package:
        packages.append(app_package)

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
""" % (app_package_name)
        
        # Create temp script
        script_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as tf:
                tf.write(script_content)
                script_path = tf.name
            
            # Run with sudo wrapper
            env = os.environ.copy()
            if self.user_password:
                env['LINEXIN_SUDO_PW'] = self.user_password
            
            cmd = f"{self.sudo_wrapper} python3 {script_path}"
            subprocess.run(cmd, shell=True, check=True, env=env)
            
        except Exception as e:
            print(f"Failed to configure pacman IgnorePkg: {e}")
        finally:
            if script_path and os.path.exists(script_path):
                os.remove(script_path)

    def cleanup_build_environment(self):
        """Moves the installer back and removes the temporary build directory"""
        if not self.tmp_build_dir or not self.original_run_file_path:
            return
        
        try:
            tmp_run_file_path = os.path.join(self.tmp_build_dir, "src", os.path.basename(self.original_run_file_path))
            
            if os.path.exists(tmp_run_file_path):
                shutil.move(tmp_run_file_path, self.original_run_file_path)
            
            if os.path.exists(self.tmp_build_dir):
                shutil.rmtree(self.tmp_build_dir)
        
        except Exception as e:
            print(_("Warning: Failed to clean up temporary build files: {}").format(e))
        finally:
            self.tmp_build_dir = None
            self.original_run_file_path = None
    
    def show_error_message(self, message):
        """Display error message"""
        self.info_label.set_markup(f'<span color="#e01b24" weight="bold">{message}</span>')
        self.fail_image.set_visible(True)
        self.success_image.set_visible(False)
        self.content_stack.set_visible_child_name("info_view")
    
    def begin_install(self, command, product_name):
        """Start the installation process"""
        self.install_started = True
        self.btn_install.set_sensitive(False)
        self.btn_install.set_visible(False)
        self.btn_toggle_progress.set_sensitive(True)
        self.btn_toggle_progress.set_visible(True)
        self.current_product = product_name
        self.error_message = None
        
        # Reset images
        self.fail_image.set_visible(False)
        self.success_image.set_visible(False)
        
        self.info_label.set_markup(f'<span size="large" weight="bold">{_("Installing {}...").format(product_name)}</span>')
        self.content_stack.set_visible_child_name("info_view")
        
        self.progress_data = ""
        self.progress_visible = False
        self.btn_toggle_progress.set_label(_("Show Progress"))
        self.output_buffer.set_text("")
        
        self.run_shell_command(command)
    
    def on_toggle_progress_clicked(self, button):
        """Handle progress toggle button"""
        self.progress_visible = not self.progress_visible
        
        if self.progress_visible:
            self.btn_toggle_progress.set_label(_("Hide Progress"))
            self.output_buffer.set_text(self.progress_data or _("[console output]"))
            self.content_stack.set_visible_child_name("progress_view")
            GLib.timeout_add(50, self.scroll_to_end)
        else:
            self.btn_toggle_progress.set_label(_("Show Progress"))
            self.content_stack.set_visible_child_name("info_view")
    
    def run_shell_command(self, command):
        """Execute shell command in a separate thread"""
        def stream_output():
            try:
                env = os.environ.copy()
                if self.user_password:
                    env['LINEXIN_SUDO_PW'] = self.user_password

                process = subprocess.Popen(command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    env=env
                )
                
                for line in iter(process.stdout.readline, ''):
                    if line:
                        self.progress_data += line
                        GLib.idle_add(self.update_output_buffer, self.progress_data)
                
                process.stdout.close()
                return_code = process.wait()
                if return_code != 0:
                    self.error_message = _("Process exited with code {}").format(return_code)
            except Exception as e:
                self.error_message = str(e)
                self.progress_data += _("\nError: {}").format(e)
                GLib.idle_add(self.update_output_buffer, self.progress_data)
            
            GLib.idle_add(self.finish_installation)
        
        threading.Thread(target=stream_output, daemon=True).start()
    
    def update_output_buffer(self, text):
        """Update the output buffer with new text"""
        if self.progress_visible:
            self.output_buffer.set_text(text)
            GLib.idle_add(self.scroll_to_end)
        return False
    
    def scroll_to_end(self):
        """Scroll text view to the end"""
        end_iter = self.output_buffer.get_end_iter()
        self.output_textview.scroll_to_iter(end_iter, 0.0, False, 0.0, 0.0)
        return False
    
    def finish_installation(self):
        """Handle installation completion"""
        self.install_started = False
        self.btn_install.set_sensitive(True)
        self.btn_install.set_visible(True)
        self.btn_toggle_progress.set_sensitive(False)
        self.btn_toggle_progress.set_visible(False)
        
        if self.error_message:
            self.info_label.set_markup(f'<span color="#e01b24" weight="bold" size="large">{_("Installation failed: ")}</span>\n{self.error_message}')
            self.btn_toggle_progress.set_sensitive(True)
            self.btn_toggle_progress.set_visible(True)
            self.fail_image.set_visible(True)
        else:
            self.info_label.set_markup(f'<span color="#2ec27e" weight="bold" size="large">{_("Successfully installed {}!").format(self.current_product)}</span>')
            self.success_image.set_visible(True)
            
            self.info_label.set_markup(f'<span color="#2ec27e" weight="bold" size="large">{_("Successfully installed {}!").format(self.current_product)}</span>')
            self.success_image.set_visible(True)
            
            # Add to IgnorePkg
            # Infer package name based on product name
            pkg_name = "davinci-resolve"
            if "Studio" in self.current_product:
                pkg_name = "davinci-resolve-studio"
                
            self.configure_pacman_ignore(pkg_name)
        
        self.content_stack.set_visible_child_name("info_view")
        self.progress_visible = False
        self.btn_toggle_progress.set_label(_("Show Progress"))
        
        # Clean up the build environment regardless of success or failure
        self.cleanup_build_environment()
        
        return False