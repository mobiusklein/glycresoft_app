import os
import glob


class FigureManager(object):
    def __init__(self, application_manager):
        self.application_manager = application_manager
        self.clean_up()
        self.call_count = 0

    def write_stream(self, analysis_id, key):
        path = self.application_manager.get_temp_path("%d-%s-fig" % (analysis_id, key))
        stream = open(path, 'wb')
        self.call_count += 1
        return stream

    def read_stream(self, analysis_id, key):
        path = self.application_manager.get_temp_path("%d-%s-fig" % (analysis_id, key))
        stream = open(path, 'rb')
        self.call_count += 1
        return stream

    def clean_up(self):
        path = self.application_manager.get_temp_path('')
        for f in glob.glob(os.path.join(path, "*-fig")):
            try:
                os.remove(f)
            except OSError:
                pass
