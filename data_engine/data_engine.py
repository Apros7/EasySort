"""
Data Engine classes
- DataRecorder: Used to record and store new videos         (POST)
- DataExplorer: Used to load, get, sort and explore data    (GET)
"""

import subprocess
import os
import cv2
import time
import logging
from datetime import datetime
import shutil
import numpy as np

from utils import get_free_filename

logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s, %(levelname)s]: %(message)s')

def get_top_folder(): return subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode('utf-8').strip("\n")

class EditorBaseModel():
    def __init__(self, cap): 
        self.cap = cap; self.should_quit = False
        self.universal_descriptions = ["Press q to quit"]

    def quit(self):
        if self.cap: self.cap.release()
        cv2.destroyAllWindows()
        self.should_quit = True

    def add_universal_description(self, frame, description):
        BLACK_BAR_WIDTH = 160
        full_description = self.universal_descriptions + description

        new_frame = np.zeros((frame.shape[0], frame.shape[1] + BLACK_BAR_WIDTH, 3), dtype=np.uint8)
        new_frame[:, :frame.shape[1], :] = frame
        new_frame[:, frame.shape[1]:, :] = (0, 0, 0)
        for i, desc in enumerate(full_description):
            cv2.putText(new_frame, desc, (frame.shape[1] + 10, 20 * (i + 1)), cv2.FONT_HERSHEY_DUPLEX, 0.5, (255, 255, 255), 1)
        return new_frame
    
    def universal_keys(self, key):
        if key == ord('q'): self.quit()

    # All Editors has to have a .run with a folder parameter

class DataRecorder(EditorBaseModel):
    def __init__(self):
        self.top_folder = get_top_folder()
        if not os.path.exists(self.top_folder): os.makedirs(self.top_folder)

        self.fps = 10
        self.recording = False
        self.frames_index = 0
        self.cap = None # buffer for later when it is actually used in .run and .quit from BaseModel
        # self.fourcc = cv2.VideoWriter_fourcc(*'avc1')
        # self.fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        super().__init__(self.cap)

    def add_description(self, frame): 
        description = ["Press 'r' to record", "Press 's' to stop recording"]
        new_frame = self.add_universal_description(frame, description)
        new_frame = cv2.rectangle(new_frame, (10, 10), (50, 30), (0, 0, 255), 2) if self.recording else cv2.rectangle(new_frame, (10, 10), (50, 30), (128, 128, 128), 2)
        return new_frame

    def record(self, start): 
        if not start and self.recording: self.recording = False; self.frames_index = 0
        if not self.recording and start: 
            self.data_folder = get_free_filename()
            if not os.path.exists(self.data_folder): os.makedirs(self.data_folder)
            self.recording = True
            self.frame_dir = os.path.join(self.top_folder, self.data_folder)

    def record_frame(self, frame):
        cv2.imwrite(os.path.join(self.frame_dir, f"frame_{self.frames_index:04d}.jpg"), frame)
        self.frames_index += 1

    def run(self, folder):
        self.cap = cv2.VideoCapture(0)
        while True:
            _, frame = self.cap.read()
            cv2.imshow("Camera", self.add_description(frame.copy()))
            if self.recording: 
                self.record_frame(frame)
            key = cv2.waitKey(1000//self.fps) & 0xFF
            if key == ord('r'): self.record(start=True)
            if key == ord('s'): self.record(start=False)
            
            self.universal_keys(key)
            if self.should_quit: break

class KeyframeEditor(EditorBaseModel):
    """
    Used to view, add and delete keyframes.
    """
    def __init__(self): pass
    def run(self, folder): return

class FrameEditor(EditorBaseModel):
    """
    Used to:
    1) delete frames before or after a certain point in a video
    2) split a long video into smaller segments
    Also has a .automate function to split automatically
    """
    def __init__(self): pass
    def run(self, folder): return

class LabelRunner(EditorBaseModel):
    """
    Used to:
    1) See current labels on a video
    2) Project keyframes labels onto the rest of the video
    3) Validate projections 
    """
    def __init__(self): pass
    def run(self, folder): return

class DataEngine():
    """
    Adds the logic to go between the menu and the appropriate editors
    """

    def __init__(self):
        self.dataMenu = DataMenu()
        self.dataRecorder = DataRecorder()
        self.keyframeEditor = KeyframeEditor()
        self.frameEditor = FrameEditor()
        self.labelRunner = LabelRunner()
        self.run()

    def run(self):
        editor_type_to_editor_object = {
            "Recorder": self.dataRecorder.run,
            "Keyframe Editor": self.keyframeEditor.run,
            "Frame Editor": self.frameEditor.run,
            "Label Runner": self.labelRunner.run
        }
        while True:
            self.dataMenu.options_menu()
            editor = editor_type_to_editor_object[self.dataMenu.editor_type]
            editor(folder = self.dataMenu.folder_to_explore)


class DataMenu():
    def __init__(self):
        self.folder_to_explore = None
        self.editor_type = None
    
    def setup_menu(self):
        cv2.namedWindow("Options Menu", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Options Menu", 640, 480)

        # Initialize menu options
        self.folders = ["new", "verified", "labelled"]
        self.editors_without_folder = ["Recorder"]
        self.editors_where_folder_is_needed = ["Keyframe Editor", "Frame Editor", "Label Runner"]
        self.editors = self.editors_without_folder + self.editors_where_folder_is_needed
        self.confirmation_choices = ["Proceed"]
        self.selected_folder = 0
        self.selected_editor = 0
        self.selected_confirmation = 0
        self.global_buttons = ["back", "quit"] # add to last elif in each _logic if you add something here

        # If this is the first round at current menu setting:
        self.first_load_of_menu = True

        # when is what shown
        #   If you change any of these, make a _menu method and a _logic method and implement into options_menu()
        #   The last line of editor_logic also has to be changed
        #   _update_selected should also be updated
        self.current_step = 0  # 0: editor, 1: folder (if necessary), 2: confirm
        self.editor_menu_step = 0
        self.folder_menu_step = 1
        self.confirmation_menu_step = 2

        self.instructions = "Use W and S to navigate, and Enter to proceed."

    def _reset_appropriate_selected(self):
        if self.current_step == self.editor_menu_step: self.selected_editor = 0
        elif self.current_step == self.folder_menu_step: self.selected_folder = 0
        elif self.current_step == self.confirmation_menu_step: self.selected_confirmation = 0

    def folder_menu(self, img):
        for i, folder in enumerate(self.folders + self.global_buttons):
            text = folder if i != self.selected_folder else f"> {folder}"
            add_on = 1 if i > len(self.folders) - 1 else 0
            cv2.putText(img, text, (20, 50 + (i + add_on) * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    def folder_logic(self, key):
        if key == ord('w'): self.selected_folder = (self.selected_folder - 1) % (len(self.folders) + len(self.global_buttons))
        elif key == ord('s'): self.selected_folder = (self.selected_folder + 1) % (len(self.folders) + len(self.global_buttons))
        elif key == ord('\r'):
            self.first_load_of_menu = True
            back_selected = self.selected_folder == len(self.folders)
            quit_selected = self.selected_folder == len(self.folders) + 1

            if back_selected: self.current_step = max(self.current_step - 1, 0)
            elif quit_selected: cv2.destroyAllWindows(); exit()
            else: self.current_step += 1

    def editor_menu(self, img):
        for i, editor in enumerate(self.editors + self.global_buttons):
            text = editor if i != self.selected_editor else f"> {editor}"
            add_on = 1 if i > len(self.editors) - 1 else 0
            cv2.putText(img, text, (20, 50 + (i + add_on) * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    def editor_logic(self, key):
        if key == ord('w'): self.selected_editor = (self.selected_editor - 1) % (len(self.editors) + len(self.global_buttons))
        elif key == ord('s'): self.selected_editor = (self.selected_editor + 1) % (len(self.editors) + len(self.global_buttons))
        elif key == ord('\r'):
            self.first_load_of_menu = True
            back_selected = self.selected_editor == len(self.editors)
            quit_selected = self.selected_editor == len(self.editors) + 1

            if back_selected: self.current_step = max(self.current_step - 1, 0)
            elif quit_selected: cv2.destroyAllWindows(); exit()
            else: self.current_step += 1 if self.editors[self.selected_editor] in self.editors_where_folder_is_needed else 2

    def confirmation_menu(self, img):
        cv2.putText(img, f"Your choices", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(img, f"Folder: {self.folders[self.selected_folder]}", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(img, f"Editor: {self.editors[self.selected_editor]}", (50, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        for i, editor in enumerate(self.confirmation_choices + self.global_buttons):
            text = editor if i != self.selected_confirmation else f"> {editor}"
            add_on = 1 if i > len(self.editors) - 1 else 0
            cv2.putText(img, text, (20, 170 + (i + add_on) * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    def confirmation_logic(self, key):
        # Return True if the menu should close and proceed to the specified editor
        if key == ord('w'): self.selected_confirmation = (self.selected_confirmation - 1) % (len(self.confirmation_choices) + len(self.global_buttons))
        elif key == ord('s'): self.selected_confirmation = (self.selected_confirmation + 1) % (len(self.confirmation_choices) + len(self.global_buttons))
        elif key == ord('\r'):
            self.first_load_of_menu = True
            back_selected = self.selected_confirmation == len(self.confirmation_choices)
            quit_selected = self.selected_confirmation == len(self.confirmation_choices) + 1

            if back_selected: self.current_step = max(self.current_step - 1, 0) # if self.folder_to_explore
            elif quit_selected: cv2.destroyAllWindows(); exit()
            else:
                self.folder_to_explore = self.folders[self.selected_folder]
                self.editor_type = self.editors[self.selected_editor]
                print(f"Selected folder: {self.folder_to_explore}, Selected editor: {self.editor_type}")
                return True

    def options_menu(self):
        self.setup_menu()
        while True:
            if self.first_load_of_menu: self.first_load_of_menu = False; self._reset_appropriate_selected()

            # Create a black background
            img = np.zeros((480, 640, 3), np.uint8)
            cv2.putText(img, self.instructions, (20, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            if self.current_step == self.editor_menu_step: self.editor_menu(img)
            elif self.current_step == self.folder_menu_step: self.folder_menu(img)
            elif self.current_step == self.confirmation_menu_step: self.confirmation_menu(img)

            # Show and get user input
            cv2.imshow("Options Menu", img)
            key = cv2.waitKey(1) & 0xFF

            # Menu logic
            if self.current_step == self.editor_menu_step: self.editor_logic(key)
            elif self.current_step == self.folder_menu_step: self.folder_logic(key)
            elif self.current_step == self.confirmation_menu_step: 
                if self.confirmation_logic(key): break

        # Close the options menu window
        cv2.destroyAllWindows()
        return

if __name__ == "__main__":
    DataEngine()