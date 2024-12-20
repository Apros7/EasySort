"""
Data Engine classes
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

class BaseModel():
    def __init__(self, cap): 
        self.cap = cap; self.should_quit = False
        self.universal_descriptions = ["Press q to quit"]

    def quit(self):
        if self.cap: self.cap.release()
        cv2.destroyAllWindows()
        self.should_quit = True

    def add_universal_description(self, frame, description):
        BLACK_BAR_WIDTH = 600
        full_description = self.universal_descriptions + description

        new_frame = np.zeros((frame.shape[0], frame.shape[1] + BLACK_BAR_WIDTH, 3), dtype=np.uint8)
        new_frame[:, :frame.shape[1], :] = frame
        new_frame[:, frame.shape[1]:, :] = (0, 0, 0)
        for i, desc in enumerate(full_description):
            cv2.putText(new_frame, desc, (frame.shape[1] + 10, 40 * (i + 1)), cv2.FONT_HERSHEY_DUPLEX, 1, (255, 255, 255), 1)
        return new_frame
    
    def universal_keys(self, key):
        if key == ord('q'): self.quit()

    # All Editors has to have a .run with a folder parameter

class DataRecorder(BaseModel):
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
        description = ["R:    to record", "S:    to stop", "", "Red = Recording", "Grey = Not recording"]
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
            aspect_ratio = frame.shape[1] / frame.shape[0]
            window_height = 1200
            window_width = int(window_height * aspect_ratio)
            frame = cv2.resize(frame, (window_width, window_height))
            cv2.imshow("Camera", self.add_description(frame.copy()))
            if self.recording: self.record_frame(frame)

            key = cv2.waitKey(1000//self.fps) & 0xFF
            if key == ord('r'): self.record(start=True)
            if key == ord('s'): self.record(start=False)
            
            self.universal_keys(key)
            if self.should_quit: self.should_quit = False; break

class EditorBaseModel(BaseModel):
    """
    Runs all the logic for working the editors, the specific keys and additional logic is then in each editor
    """
    def __init__(self):
        self._folder_to_explore = "new"
        self.allowed_folders = ["new", "verified", "labelled"]
        self.data_folder = os.path.join(get_top_folder(), "data", self._folder_to_explore)
        self.fps = 10
        self.pause = False
        self.file_to_view = None

        # EDITORS
        self.keyframeEditor = KeyframeEditor()
        self.frameEditor = FrameEditor(cap = None)
        self.auditer = Auditer(cap = None)

        self.editors_name_to_state_method = {
            "Keyframes": (self.keyframeEditor.run, self.keyframeEditor.description),
            "Splitting and cutting": (self.frameEditor.run, self.frameEditor.description),
            "Approve or deny": (self.auditer.run, self.auditer.description)
        }

        ## Choose editor
        self.state_method = None
        self.description_method = None
        self._reset_state()
        self.file_index = 0
        self.files = []

        super().__init__(cap = None)
    
    def _load(self): self.files = sorted(os.listdir(self.data_folder)); print("SELF.FILES \n ", self.files)
    def _reset_state(self): 
        self.state_method = self.choose_editor_state_logic
        self.description_method = lambda x: [f"{i}:   for {editor_name}" for i, editor_name in enumerate(self.editors_name_to_state_method.keys())]

    def _reload_files_and_frames(self):
        self.frame_index = 0
        self.file_index = 0
        self._load()
        self._load_frame_files()

    def universal_editor_description(self): return [
        "", 
        "ESC:  choose editors", 
        "R:    reset", 
        "P:    (un)pause",
        "B:    back 1 frame", 
        "N:    next 1 frames", 
        "I:    go to previous video", 
        "O:    go to the next video",
        "", 
        f"Playing video: {self.file_index + 1}/{len(self.files)}", 
        f"Frame:         {self.frame_index + 1}/{len(self.frame_files)}"
    ]

    def change_folder_to_explore(self, folder):
        if folder not in self.allowed_folders: raise LookupError(f"Folder has to be in {self.allowed_folders}, but is {folder}")
        self._folder_to_explore = folder
        self.data_folder = os.path.join(get_top_folder(), "data", self._folder_to_explore)
        self.file_index = 0
        self._load()

    def editor_base_keys(self, key): 
        if key == 27: self._reset_state() # if key == esc
        if key == ord('r'): self.frame_index = 0; self.pause = False
        if key == ord('p'): self.pause = not self.pause
        if key == ord('b'): self.pause = True; self.frame_index -= 1
        if key == ord('n'): self.pause = True; self.frame_index += 1
        if key == ord("i"): self.file_index = max(0, self.file_index - 1)
        if key == ord("o"): self.file_index = min(self.file_index + 1, len(self.files) - 1)

        if not self.pause: self.frame_index += 1

        if self.frame_index >= len(self.frame_files): self.frame_index = len(self.frame_files) - 1
        if self.frame_index < 0: self.frame_index = 0
        
    def choose_editor_state_logic(self, key, EditorBaseModel):
        for i, (editor_state_method, editor_description_method) in enumerate(self.editors_name_to_state_method.values()):
            if key == ord(f"{i}"): self.state_method = editor_state_method; self.description_method = editor_description_method

    def add_descrition(self, frame, editor_description): 
        description = [""] + editor_description(self)
        new_frame = self.add_universal_description(frame, self.universal_editor_description() + description)
        return new_frame
    
    def _load_frame_files(self): 
        self.file_to_view = os.path.join(self.data_folder, self.files[self.file_index])
        self.frame_files = sorted([frame for frame in os.listdir(self.file_to_view) if frame[-4:] == ".jpg"])


    def run(self, folder):
        self.change_folder_to_explore(folder)
        current_file = self.file_index
        self.file_to_view = os.path.join(self.data_folder, self.files[self.file_index])
        self._load_frame_files()
        self.frame_index = 0

        while True:
            frame_path = os.path.join(self.file_to_view, self.frame_files[self.frame_index])
            frame = cv2.imread(frame_path)
            if frame is None: self.error()
            cv2.imshow("frame", self.add_descrition(frame, self.description_method))
            key = cv2.waitKey(1000//self.fps) & 0xFF

            self.state_method(key, self)
            self.editor_base_keys(key)
            self.universal_keys(key)
            if self.should_quit: self.should_quit = False; break
            if self.file_index != current_file:
                current_file = self.file_index
                file_to_view = os.path.join(self.data_folder, self.files[self.file_index])
                self.frame_index = 0
                self._load_frame_files()

class KeyframeEditor(BaseModel):
    """
    Used to view, add and delete keyframes.
    Only works on verified files
    """
    def __init__(self):
        self.keyframes = None
        self.uploaded_keyframes = None
        self.loaded_keyframes_path = None
        super().__init__(cap=None)

    def save_file(self, path: str, content: list): 
        with open(path, 'w') as f:
            for obj in content:
                f.write(f"{obj}\n")

    def read_file(self, path: str):
        if not os.path.exists(path):
            with open(path, 'w') as f: pass
            return []
        else:
            with open(path, 'r') as f:
                return [int(line.strip()) for line in f.readlines()]

    def get_keyframes_path(self, EditorBaseModel: EditorBaseModel):
        return os.path.join(EditorBaseModel.data_folder, EditorBaseModel.files[EditorBaseModel.file_index], "keyframes.txt")

    def add_keyframe(self, EditorBaseModel: EditorBaseModel):
        keyframe_to_add = EditorBaseModel.frame_index
        self.load_keyframes(EditorBaseModel)
        
        if keyframe_to_add not in self.keyframes:
            self.keyframes.append(keyframe_to_add)
            self.keyframes.sort()
            self.save_keyframes(EditorBaseModel)
        
        self.load_keyframes(EditorBaseModel, force = True)

    def delete_keyframe(self, EditorBaseModel: EditorBaseModel):
        keyframe_to_delete = EditorBaseModel.frame_index
        self.load_keyframes(EditorBaseModel)
        
        if keyframe_to_delete in self.keyframes:
            self.keyframes.remove(keyframe_to_delete)
            self.save_keyframes(EditorBaseModel)

        self.load_keyframes(EditorBaseModel, force = True)

    def save_keyframes(self, EditorBaseModel: EditorBaseModel):
        keyframes_path = self.get_keyframes_path(EditorBaseModel)
        self.save_file(keyframes_path, self.keyframes)

    def load_keyframes(self, EditorBaseModel: EditorBaseModel, force: bool = False):
        if self.keyframes is not None and not force: return
        keyframes_path = self.get_keyframes_path(EditorBaseModel)
        self.loaded_keyframes_path = keyframes_path
        self.keyframes = self.read_file(keyframes_path)

    def prep_to_upload_folder(self) -> str:
        to_upload_path = os.path.join(get_top_folder(), "data", "to_upload")
        if not os.path.exists: os.makedirs(to_upload_path)
        for file in os.listdir(to_upload_path): os.remove(os.path.join(to_upload_path, file))
        return to_upload_path

    def prepare_upload(self, EditorBaseModel: EditorBaseModel):
        if EditorBaseModel._folder_to_explore != "verified": return
        to_upload_path = self.prep_to_upload_folder()

        for file in EditorBaseModel.files:
            # Reading this specific files keyframes, uploaded_keyframes and frame_files
            keyframes_path = os.path.join(EditorBaseModel.data_folder, file, "keyframes.txt")
            self.keyframes = self.read_file(keyframes_path)
            uploaded_keyframes_path = os.path.join(EditorBaseModel.data_folder, file, "uploaded_keyframes.txt")
            uploaded_keyframes = self.read_file(uploaded_keyframes_path)
            to_upload = [n for n in self.keyframes if n not in uploaded_keyframes]
            frame_files_path = os.path.join(EditorBaseModel.data_folder, file)
            frame_files = sorted([frame for frame in os.listdir(frame_files_path) if frame[-4:] == ".jpg"])

            if len(to_upload) == 0: continue
            self.uploaded_keyframes = list(set(self.keyframes + uploaded_keyframes))

            for i in to_upload:
                frame_file = frame_files[i]
                src_path = os.path.join(EditorBaseModel.data_folder, file, frame_file)
                dst_path = os.path.join(to_upload_path, file + "__" + frame_file)
                shutil.copy(src_path, dst_path)

            self.save_file(uploaded_keyframes_path, self.uploaded_keyframes)

    
    def description(self, EditorBaseModel: EditorBaseModel): 
        self.load_keyframes(EditorBaseModel)
        is_current_frame_keyframe = EditorBaseModel.frame_index in self.keyframes
        return [
            "",
            "| -------------------------- |",
            f"Current frame {"is" if is_current_frame_keyframe else "not"} a keyframe",
            "| -------------------------- |",
            ""
            "A: Add current frame as keyframe",
            "D: Delete current keyfranme",
            "P: Prep for upload" if EditorBaseModel._folder_to_explore == "verified" else "",
            "L: Project labels from labelled keyframes"
            "", 
            "Current keyframes:",
            f"{[i+1 for i in self.keyframes]}"
        ]
    
    def project_labels(self, EditorBaseModel: EditorBaseModel):
        # open the yolo dataset, get all keyframes and save their respective labels, project them onto the full videos, delete yolo dataset
        return

    def run(self, key, EditorBaseModel):
        if self.loaded_keyframes_path != self.get_keyframes_path(EditorBaseModel): 
            self.load_keyframes(EditorBaseModel, force = True)
        if key == ord("a"): self.add_keyframe(EditorBaseModel)
        if key == ord("d"): self.delete_keyframe(EditorBaseModel)
        if key == ord("p"): self.prepare_upload(EditorBaseModel)
        if key == ord("l"): self.project_labels(EditorBaseModel)
        return

class FrameEditor(BaseModel):
    """
    Used to:
    1) delete frames before or after a certain point in a video
    2) split a long video into smaller segments
    Also has a .automate function to split automatically
    """
    def description(self, EditorBaseModel): return [
        "D:    delete previous frames",
        "F:    delete future frames",
        "S:    split future frames",
    ]
    
    def delete_previous_frames(self, EditorBaseModel: EditorBaseModel, from_index: int):
        files_to_delete = EditorBaseModel.frame_files[:from_index]
        for file in files_to_delete:
            os.remove(os.path.join(EditorBaseModel.file_to_view, file))

    def delete_future_frames(self, EditorBaseModel: EditorBaseModel, from_index: int):
        files_to_delete = EditorBaseModel.frame_files[from_index + 1:]
        for file in files_to_delete:
            os.remove(os.path.join(EditorBaseModel.file_to_view, file))
    
    def copy_future_frames(self, EditorBaseModel: EditorBaseModel, from_index: int):
        folder = EditorBaseModel.data_folder
        new_filename = get_free_filename(EditorBaseModel.file_to_view.split("_")[-2])
        filename = os.path.basename(new_filename)
        files_to_move = EditorBaseModel.frame_files[from_index + 1:]

        new_dir = os.path.join(folder, filename)
        if not os.path.exists(new_dir):
            os.makedirs(new_dir)
            
        for file in files_to_move:
            shutil.move(os.path.join(EditorBaseModel.file_to_view, file), new_dir)

    def run(self, key, EditorBaseModel: EditorBaseModel): 
        if key == ord("d"): 
            self.delete_previous_frames(EditorBaseModel, EditorBaseModel.frame_index)
            EditorBaseModel._reload_files_and_frames()

        if key == ord("f"): 
            self.delete_future_frames(EditorBaseModel, EditorBaseModel.frame_index)
            EditorBaseModel._reload_files_and_frames()

        if key == ord("s"): 
            self.copy_future_frames(EditorBaseModel, EditorBaseModel.frame_index)
            # self.delete_future_frames(EditorBaseModel, EditorBaseModel.frame_index)
            EditorBaseModel._reload_files_and_frames()

class Auditer(BaseModel):
    """
    Used to move the videos:
    1) from new to verified
    2) delete from new
    3) from verified to new

    Used to:
    1) See current labels on a video
    2) Project keyframes labels onto the rest of the video
    3) Validate projections 
    """

    def description(self, EditorBaseModel: EditorBaseModel):
        if EditorBaseModel._folder_to_explore == "new": return self.description_new()
        if EditorBaseModel._folder_to_explore == "verified": return self.description_verified()
        return []

    def description_new(self): return [
        "A:    Move video to 'Verified'",
        "D:    Delete"
    ]
    
    def description_verified(self): return [
        "A:    Move video to 'Labelled'",
        "D:    Move back to 'New'"
    ]
    
    def run_new(self, key, EditorBaseModel: EditorBaseModel):
        if key == ord("a"):
            file_path = os.path.join(EditorBaseModel.data_folder, EditorBaseModel.files[EditorBaseModel.file_index])
            verified_file_path = os.path.join(get_top_folder(), "data", "verified")
            new_file_path = os.path.join(verified_file_path, EditorBaseModel.files[EditorBaseModel.file_index])
            shutil.move(file_path, new_file_path)
            EditorBaseModel._reload_files_and_frames()
        if key == ord("d"): 
            file_path = os.path.join(EditorBaseModel.data_folder, EditorBaseModel.files[EditorBaseModel.file_index])
            if os.path.exists(file_path): 
                shutil.rmtree(file_path)
                EditorBaseModel._reload_files_and_frames()
    
    def run_verified(self, key, EditorBaseModel: EditorBaseModel):
        if key == ord("a"):
            # TODO:
            # check if video has ben projectet with keyframes
            # if not then maybe project and inform the user
            # and let them potentially approve again
            pass
        if key == ord("d"): 
            file_path = os.path.join(EditorBaseModel.data_folder, EditorBaseModel.files[EditorBaseModel.file_index])
            new_folder_file_path = os.path.join(get_top_folder(), "data", "new")
            new_file_path = os.path.join(new_folder_file_path, EditorBaseModel.files[EditorBaseModel.file_index])
            shutil.move(file_path, new_file_path)
            EditorBaseModel._reload_files_and_frames()

    def run(self, key, EditorBaseModel: EditorBaseModel): 
        if EditorBaseModel._folder_to_explore == "new": return self.run_new(key, EditorBaseModel)
        if EditorBaseModel._folder_to_explore == "verified": return self.run_verified(key, EditorBaseModel)        
        return

class DataEngine():
    """
    Adds the logic to go between the menu and the appropriate editors
    """

    def __init__(self):
        self.dataMenu = DataMenu()
        self.dataRecorder = DataRecorder()
        self.editor = EditorBaseModel()
        self.run()

    def run(self):
        editor_type_to_editor_object = {
            "Record": self.dataRecorder.run,
            "Edit Videos": self.editor.run
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
        self.editors_without_folder = ["Record"]
        self.editors_where_folder_is_needed = ["Edit Videos"]
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
            else: 
                self.current_step += 1 if self.editors[self.selected_editor] in self.editors_where_folder_is_needed else 2
                self.selected_folder = 0 if self.editors[self.selected_editor] in self.editors_without_folder else self.selected_folder

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

            if back_selected: 
                to_subtract = 2 if self.editors[self.selected_editor] in self.editors_without_folder else 1
                self.current_step = max(self.current_step - to_subtract, 0) 
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
    
## WORKFLOW
    
"""
Workflow is as follows:
1) Record the videos
2) Split in sections 
2.5) Accept good splits in FrameEditor
3) Cut each split to not have unnecessary parts
4) Add keyframes
5) External: Label keyframes
6) Run labelrunner to project keyframes
7) Confirm the labels to put into labelled (these videos will now be used for training)

Todo:
[x] Record
[x] Split
[x] Accept
[x] Cut splits
[x] Keyframes
[ ] Label keyframes (upload and download)
[ ] Project keyframes
[ ] Confirm labels
"""

if __name__ == "__main__":
    DataEngine()