#!/usr/bin/env python3

import csv
import sys
from PyQt4 import QtCore, QtGui

################################################################
# Data model
################################################################

class MeasurementsData(QtCore.QObject):

    dataChanged = QtCore.pyqtSignal()

    def __init__(self, filename, **kwargs):
        super(MeasurementsData, self).__init__(**kwargs)

        self.filename = filename

        self.col_titles = None
        self.metadata_cols = None
        self.measurement_cols = None
        self.table = None
        self.path_map = None

        self.dirty = False

    def _load_header(self, row):
        self.col_titles = row
        self.metadata_cols = []
        self.measurement_cols = []

        for idx, title in enumerate(row):
            title = row[idx]

            name = title.strip()

            record = {'idx': idx,
                      'name': name,
                      'title': title,
                      'mutable': False}

            # Metadata column names end with '='
            if name.endswith('='):
                record['name'] = name[0:-1]
                self.metadata_cols.append(record)

            # Measurement column names end with '?'
            elif name.endswith('?'):
                record['name'] = name[0:-1]
                record['mutable'] = True
                self.measurement_cols.append(record)

            else:
                self.measurement_cols.append(record)

    def _load(self):
        # Read in the CSV data
        with open(self.filename, 'rb') as in_fp:
            csv_reader = csv.reader(in_fp)

            # The first row should contain column names
            self._load_header(next(csv_reader))

            # The remaining rows should contain data
            self.table = list(csv_reader)

        # Build the path map
        self.path_map = {}

        for row_idx, row in enumerate(self.table):
            row = self.table[row_idx]

            path = []
            for record in self.metadata_cols:
                path.append(row[record['idx']])

            parent = self.path_map
            for element in path:
                if not parent.has_key(element):
                    parent[element] = {}
                parent = parent[element]

            parent['_index_'] = row_idx

        self.dirty = False
        print("Loaded from '{}'".format(self.filename))
        self.dataChanged.emit()

    def _lazy_load(self):
        if self.table is None:
            self._load()

    def _save(self):
        # Write out the CSV data
        with open(self.filename, 'wb') as out_fp:
            csv_writer = csv.writer(out_fp)

            csv_writer.writerow(self.col_titles)
            csv_writer.writerows(self.table)

        self.dirty = False
        print("Saved to '{}'".format(self.filename))

    def _eval_path_map(self, path):
        self._lazy_load()

        parent = self.path_map
        for element in path:
            if not parent.has_key(element):
                return None
            parent = parent[element]
        return parent

    def metadata_keys(self):
        self._lazy_load()
        return [x["name"] for x in self.metadata_cols]

    def metadata_values(self, path):
        parent = self._eval_path_map(path)
        if parent is None:
            return []

        return parent.keys()

    def measurement_keys(self):
        self._lazy_load()
        return [x['name'] for x in self.measurement_cols]

    def is_measurement_mutable(self, key):
        self._lazy_load()
        for record in self.measurement_cols:
            if record['name'] == key:
                return record['mutable']
        return False

    def _get_row_index(self, path):
        return self._eval_path_map(path).get('_index_')

    def _get_col_index(self, key):
        for record in self.measurement_cols:
            if record['name'] == key:
                return record['idx']
        return None

    def validate_path(self, path, partial=False):
        self._lazy_load()

        parent = self._eval_path_map(path)
        if partial:
            return parent is not None
        else:
            return parent.get('_index_') is not None

    def paths_with_prefix(self, prefix=[]):
        parent = self._eval_path_map(prefix)

        if parent.get('_index_') is not None:
            yield prefix
            return

        for k in parent.keys():
            for p in self.paths_with_prefix(prefix + [k]):
                yield p

    def get_measurement(self, path, key):
        self._lazy_load()
        row_idx = self._get_row_index(path)
        col_idx = self._get_col_index(key)

        assert row_idx is not None
        assert col_idx is not None
        assert len(self.table) > row_idx

        if col_idx >= len(self.table[row_idx]):
            return ''

        return self.table[row_idx][col_idx]

    def set_measurement(self, path, key, value, partial=False):

        self._lazy_load()

        def row_indices(pmap=None, path=None):

            assert path is not None

            if pmap is None:
                print("{} - {} - {}".format(path, key, value))
                pmap = self._eval_path_map(path)
                if not partial:
                    assert pmap.get('_index_') is not None

            if pmap.has_key('_index_'):
                yield (path, pmap['_index_'])
            else:
                for k in pmap.iterkeys():
                    sub_path = path + [k]
                    for pair in row_indices(pmap=pmap[k], path=sub_path):
                        yield pair

        col_idx = self._get_col_index(key)

        for row_path, row_idx in row_indices(path=path):

            print("{} - {} - {}".format(row_path, key, value))

            assert row_idx is not None
            assert col_idx is not None
            assert len(self.table) > row_idx

            while col_idx >= len(self.table[row_idx]):
                self.table[row_idx].append('')

            self.table[row_idx][col_idx] = value

        self.dirty = True
        self.dataChanged.emit()

    def commit(self):
        self._save()
        self._load()

    def revert(self):
        self._load()

    def is_modified(self):
        return self.dirty

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
            previous.currentIndexChanged.connect(self.update)

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

    def currentPath(self):
        path = self._full_path()
        if None in path:
            return path[0:path.index(None)]
        else:
            return path

    def update(self):
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
        for idx, name in enumerate(self.model.measurement_keys()):
            grid.addWidget(QtGui.QLabel(name.replace("_"," ")), idx, 0)

            if self.model.is_measurement_mutable(name):
                editor = EditorComboBox(self.model, name)
            else:
                editor = EditorDisplay(self.model, name)

            grid.addWidget(editor, idx, 1)
            self.editors.append(editor)

        grid.setColumnStretch(1, 1)

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

        navigator = NavigatorWidget(model=self.model)
        editor = EditorWidget(model=self.model)

        hbox.addWidget(navigator, stretch=1)
        hbox.addWidget(editor, stretch=2)

        # Control widgets
        hbox = QtGui.QHBoxLayout()
        vbox.addLayout(hbox)

        hbox.addStretch(1)

        self.save_button = QtGui.QPushButton("Save changes")
        hbox.addWidget(self.save_button)

        navigator.currentPathChanged.connect(editor.setCurrentPath)

        self.save_button.clicked.connect(self.model.commit)

    def update(self):
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
