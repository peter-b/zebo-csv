import csv
from PyQt4 import QtCore

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

    def get_filename(self):
        return self.filename

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
        self._emit_data_changed()

    def _emit_data_changed(self):
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
        self._emit_data_changed()

    def commit(self):
        self._save()
        self._load()

    def revert(self):
        self._load()

    def is_modified(self):
        return self.dirty

    def _path_at_row(self, row_idx):
        """Get the path corresponding to the specified row of the data table"""
        row = self.table[row_idx]

        path = []
        for record in self.metadata_cols:
            path.append(row[record['idx']])
        return path

    def path_next(self, path):
        row_idx = self._get_row_index(path)

        if row_idx is None:
            return None

        row_idx += 1 # Next row
        if row_idx >= len(self.table):
            return None

        return self._path_at_row(row_idx)

    def path_previous(self, path):
        row_idx = self._get_row_index(path)

        if row_idx is None:
            return None

        row_idx -= 1 # Previous row
        if row_idx < 0:
            return None

        return self._path_at_row(row_idx)

# Local variables:
# indent-tabs-mode: nil
# tab-width: 4
# End:
