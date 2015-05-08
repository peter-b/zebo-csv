#!/usr/bin/env python3

import sys
from PyQt4 import QtCore, QtGui
from zebo.measurements import MeasurementsData

################################################################
# User interface
################################################################

class NavigatorComboBox(QtGui.QComboBox):

    currentPathChanged = QtCore.pyqtSignal()

    def __init__(self, model, previous=None, **kwargs):
        super(NavigatorComboBox, self).__init__(**kwargs)

        self.model = model
        self.previous = previous
        self.last_value = ''

        # Make sure that if the previous box changes, this get updated
        if previous is not None:
            previous.currentIndexChanged.connect(self._prev_index_changed)

        # Make sure that if this gets updated, this widget emits a
        # path change signal
        self.currentIndexChanged.connect(self._emit_path_changed)

        # Make sure that if the data changes, this widget gets updated
        if previous is None:
            self.model.dataChanged.connect(self.update)

        self.update()

    def _emit_path_changed(self):
        self.currentPathChanged.emit()

    def _parent_path(self):
        path = []
        if self.previous is not None:
            path = self.previous._full_path()
        return path

    def _full_path(self):
        path = self._parent_path()
        if self.currentIndex() < 1:
            path.append(None)
        else:
            path.append(str(self.currentText()))
        return path

    def _depth(self, acc=0):
        if self.previous is None:
            return acc
        return self.previous._depth(acc + 1)

    def currentPath(self):
        path = self._full_path()
        if None in path:
            return path[0:path.index(None)]
        else:
            return path

    def setCurrentPath(self, path):
        # Make sure that the path is full for this level
        depth = self._depth()
        full_path = []
        for i in range(depth+1):
            if i >= len(path):
                full_path.append(None)
            else:
                full_path.append(path[i])

        # Recurse up to the root first, and let that update, then
        # cascade back down
        if self.previous is not None:
            self.previous.currentIndexChanged.disconnect(self._prev_index_changed)
            self.previous.setCurrentPath(full_path[:-1])
            self.previous.currentIndexChanged.connect(self._prev_index_changed)

        # Force update of this element
        self.update(full_path[-1])

    def _prev_index_changed(self):
        self.update()

    def update(self, move_to=None):
        if move_to is not None:
            current_value = move_to
        else:
            current_value = str(self.currentText())

        if current_value == '':
            current_value = self.last_value
        self.last_value = current_value

        path = self._parent_path()

        # Set the new list of values
        self.blockSignals(True)

        values = self.model.metadata_values(path)

        def try_int(value):
            try:
                return int(value)
            except:
                return 0

        values.sort(key=try_int)
        values = ['(All)'] + values

        self.clear()
        self.addItems(values)

        # This makes sure that we always get a currentIndexChanged
        # signal emission
        self.setCurrentIndex(-1)

        self.blockSignals(False)

        # Try to get back to the original value
        try:
            self.setCurrentIndex(values.index(current_value))
        except:
            self.setCurrentIndex(0)

class NavigatorWidget(QtGui.QWidget):

    currentPathChanged = QtCore.pyqtSignal(list)

    def __init__(self, model, **kwargs):
        super(NavigatorWidget, self).__init__(**kwargs)

        self.model = model

        self._init_ui()

    def _init_ui(self):
        vbox = QtGui.QVBoxLayout()
        self.setLayout(vbox)

        # Layout the controls in a grid
        grid = QtGui.QGridLayout()
        vbox.addLayout(grid)

        # Create a label and combobox for each metadata item
        self.comboboxes = []

        combobox = None
        for idx, name in enumerate(self.model.metadata_keys()):
            grid.addWidget(QtGui.QLabel(name.replace("_"," ")), idx, 0)

            # The comboboxes are chained together
            combobox = NavigatorComboBox(model=self.model, previous=combobox)

            grid.addWidget(combobox, idx, 1)
            self.comboboxes.append(combobox)

        grid.setColumnStretch(1, 1)
        vbox.addStretch(1)

        # It's enough to connect to the last combobox in the chain in
        # order to get updates every time the selected path changes
        combobox.currentIndexChanged.connect(self._emit_path_changed)

    def currentPath(self):
        return self.comboboxes[-1].currentPath()

    def setCurrentPath(self, path):
        self.comboboxes[-1].setCurrentPath(path)

    def _emit_path_changed(self):
        self.currentPathChanged.emit(self.currentPath())

class EditorDisplay(QtGui.QLabel):

    MULTI_VALUE_TEXT="(Multiple values)"

    def __init__(self, model, name, **kwargs):
        super(EditorDisplay, self).__init__(**kwargs)

        self.model = model
        self.name = name
        self.path = []

        self.update()

    def update(self):
        self.setText('')

        if not self.model.validate_path(self.path, partial=True):
            # Invalid path
            return

        if not self.model.validate_path(self.path, partial=False):
            # Multiple rows selected
            seen = set()
            for path in self.model.paths_with_prefix(self.path):
                value = self.model.get_measurement(path, self.name)
                if value in seen:
                    continue
                seen.add(value)

            values = sorted(seen)

            if len(values) > 1:
                self.setText(self.MULTI_VALUE_TEXT)
            elif len(values) == 1:
                self.setText(values[0])

        else:
            # Single row selected
            self.setText(self.model.get_measurement(self.path, self.name))

    def setCurrentPath(self, path):
        if path == self.path:
            return
        self.path = path
        self.update()

class EditorComboBox(QtGui.QComboBox):

    NO_VALUE_TEXT="(No value)"
    MULTI_VALUE_TEXT="(Multiple values)"

    def __init__(self, model, name, **kwargs):
        super(EditorComboBox, self).__init__(**kwargs)

        self.model = model
        self.name = name
        self.path = []

        self.setEditable(True)
        self.lineEdit().setPlaceholderText(self.NO_VALUE_TEXT)

        self.update()

    def update(self):
        try:
            self.editTextChanged.disconnect(self._update_model)
        except TypeError:
            pass

        self.clear()

        if not self.model.validate_path(self.path, partial=True):
            # Invalid path
            self.setEnabled(False)
            return

        if not self.model.validate_path(self.path, partial=False):
            # Multiple rows selected
            seen = set()
            for path in self.model.paths_with_prefix(self.path):
                value = self.model.get_measurement(path, self.name)
                if value in seen:
                    continue
                seen.add(value)

            values = sorted(seen)
            self.addItems(values)

            if len(values) > 1:
                self.insertItem(0, '')
                self.lineEdit().setPlaceholderText(self.MULTI_VALUE_TEXT)
                self.setCurrentIndex(0)

            self.setEnabled(True)
            self.setEditable(True)

            # Make sure that the model gets updated when the user edits
            # the value.
            self.editTextChanged.connect(self._update_model)

        else:
            # Single row selected
            self.lineEdit().setPlaceholderText(self.NO_VALUE_TEXT)
            self.setEnabled(True)
            self.setEditText(self.model.get_measurement(self.path, self.name))

            # Make sure that the model gets updated when the user edits
            # the value.
            self.editTextChanged.connect(self._update_model)

    def setCurrentPath(self, path):
        if path == self.path:
            return
        self.path = path
        self.update()

    def _update_model(self):
        new_value = self.currentText()

        if not self.model.validate_path(self.path, partial=False):
            # Multiple rows selected
            self.model.set_measurement(self.path, self.name, new_value, partial=True)
        else:
            # Single row selected
            self.model.set_measurement(self.path, self.name, new_value)

class EditorWidget(QtGui.QWidget):

    def __init__(self, model, **kwargs):
        super(EditorWidget, self).__init__(**kwargs)

        self.model = model

        self._init_ui()

    def _init_ui(self):
        # Overall vertical layout
        vbox = QtGui.QVBoxLayout()
        self.setLayout(vbox)

        # Layout the controls in a grid
        grid = QtGui.QGridLayout()
        vbox.addLayout(grid)

        # Create a label and editor combobox for each measurement item
        self.editors = []

        all_keys = [(x, self.model.is_measurement_mutable(x))
                     for x in self.model.measurement_keys()]

        immutable_keys = [x[0] for x in all_keys if not x[1]]
        for idx, name in enumerate(immutable_keys):
            grid.addWidget(QtGui.QLabel(name.replace("_"," ")), idx, 0)
            editor = EditorDisplay(self.model, name)
            grid.addWidget(editor, idx, 1)
            self.editors.append(editor)

        grid.setColumnStretch(1, 1)

        mutable_keys = [x[0] for x in all_keys if x[1]]
        for idx, name in enumerate(mutable_keys):
            grid.addWidget(QtGui.QLabel(name.replace("_"," ")), idx, 2)
            editor = EditorComboBox(self.model, name)
            grid.addWidget(editor, idx, 3)
            self.editors.append(editor)

        grid.setColumnStretch(3, 1)

        vbox.addStretch(1)

    def setCurrentPath(self, path):
        for e in self.editors:
            e.setCurrentPath(path)

class TopLevelWidget(QtGui.QWidget):
    def __init__(self, model, **kwargs):
        super(TopLevelWidget, self).__init__(**kwargs)

        self.model = model

        self._init_ui()

        self.model.dataChanged.connect(self.update)

        self.update()

    def _init_ui(self):
        vbox = QtGui.QVBoxLayout()
        self.setLayout(vbox)

        # Main widgets
        hbox = QtGui.QHBoxLayout()
        vbox.addLayout(hbox, stretch=1)

        self.navigator = NavigatorWidget(model=self.model)
        self.editor = EditorWidget(model=self.model)

        hbox.addWidget(self.navigator, stretch=1)
        hbox.addWidget(self.editor, stretch=2)

        # Control widgets
        hbox = QtGui.QHBoxLayout()
        vbox.addLayout(hbox)

        self.prev_button = QtGui.QPushButton("Previous")
        hbox.addWidget(self.prev_button)

        self.next_button = QtGui.QPushButton("Next")
        hbox.addWidget(self.next_button)

        hbox.addStretch(1)

        self.save_button = QtGui.QPushButton("Save changes")
        hbox.addWidget(self.save_button)

        self.navigator.currentPathChanged.connect(self.editor.setCurrentPath)
        self.navigator.currentPathChanged.connect(self._update_nav)

        self.prev_button.clicked.connect(self._previous)
        self.next_button.clicked.connect(self._next)
        self.save_button.clicked.connect(self.model.commit)

    def _previous(self):
        prev_path = self.model.path_previous(self.navigator.currentPath())
        if prev_path is None:
            return
        self.navigator.setCurrentPath(prev_path)

    def _next(self):
        next_path = self.model.path_next(self.navigator.currentPath())
        if next_path is None:
            return
        self.navigator.setCurrentPath(next_path)

    def _update_nav(self, path):
        prev_path = self.model.path_previous(path)
        self.prev_button.setEnabled(prev_path is not None)

        next_path = self.model.path_next(path)
        self.next_button.setEnabled(next_path is not None)

    def update(self):
        if self.model.is_modified():
            title = "{} [modified] - Zebo"
        else:
            title = "{} - Zebo"
        self.setWindowTitle(title.format(self.model.get_filename()))

        self._update_nav(self.navigator.currentPath())
        self.save_button.setEnabled(self.model.is_modified())

if __name__ == '__main__':
    app = QtGui.QApplication([])

    if len(sys.argv) < 2:
        chosen_filename = QtGui.QFileDialog.getOpenFileNameAndFilter(
            None,
            "Select a CSV file to open",
            QtCore.QDir.currentPath(),
            "CSV files (*.csv)")

        filename = chosen_filename[0]
    else:
        filename = sys.argv[1]

    if filename == '':
        sys.exit()

    mdata = MeasurementsData(filename)

    w = TopLevelWidget(model=mdata)
    w.show()
    sys.exit(app.exec_())

# Local variables:
# indent-tabs-mode: nil
# tab-width: 4
# End:
