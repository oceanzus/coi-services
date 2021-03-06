import re
import os
import numpy
import urllib
from pyon.util.log import log

from coverage_model.coverage import SimplexCoverage
from pydap.model import DatasetType,BaseType, GridType, StructureType
from pydap.handlers.lib import BaseHandler

class Handler(BaseHandler):

    #extensions = re.compile(r"^.*\.cov", re.IGNORECASE)
    extensions = re.compile(r'^.*[0-9A-Za-z]{32}', re.IGNORECASE)

    def __init__(self, filepath):
        self.filepath = filepath

    def parse_constraints(self, environ):
        base = os.path.split(self.filepath)
        coverage = SimplexCoverage.load(base[0], base[1])

        atts = {}
        atts['title'] = coverage.name
        dataset = DatasetType(coverage.name) #, attributes=atts)
        fields, queries = environ['pydap.ce']
        queries = filter(bool, queries)  # fix for older version of pydap

        all_vars = coverage.list_parameters()
        t = []

        for param in all_vars:
            if numpy.dtype(coverage.get_parameter_context(param).param_type.value_encoding).char == 'O':
                t.append(param)
        [all_vars.remove(i) for i in t]

        time_context = coverage.get_parameter_context(coverage.temporal_parameter_name)
        time_fill_value = time_context.fill_value
        time_data = coverage.get_parameter_values(coverage.temporal_parameter_name)
        fill_index = -1
        try:
            fill_index = numpy.where(time_data == time_fill_value)[0][0]
        except IndexError:
            pass

        # If no fields have been explicitly requested, of if the sequence
        # has been requested directly, return all variables.

        if not fields:
            fields = [[(name, ())] for name in all_vars]

        for var in fields:
            target = dataset
            while var:
                name, slice_ = var.pop(0)
                covname = urllib.unquote(name)
                param = coverage.get_parameter(covname)

                #need to truncate slice here in case time has fill values
                if len(slice_) == 0 and fill_index >= 0:
                    slice_ = slice(0, fill_index, 1)

                if len(slice_) == 1:
                    slice_ = slice_[0]

                    if fill_index > slice_.start:
                        continue

                    if fill_index > slice_.stop:
                        slice_.stop = fill_index

                if param.is_coordinate or target is not dataset:
                    target[name] = get_var(coverage,name,slice_)
                elif var:
                    target.setdefault(name, StructureType(name=name, attributes={'units':coverage.get_parameter_context(name).uom}))
                    target = target[name]
                else:  # return grid
                    grid = target[name] = GridType(name=name)
                    grid[name] = get_var(coverage,name, slice_)

                    dim = coverage.temporal_parameter_name 
                    grid[dim] = get_var(coverage,dim,slice_)
        dataset._set_id()
        dataset.close = coverage.close
        return dataset

def get_var(coverage,name,slice_):
    data = coverage.get_parameter_values(name,tdoa=slice_)
    attrs = {'units': coverage.get_parameter_context(name).uom}
    dims = (coverage.temporal_parameter_name,)
    
    
    log.debug( 'name=%s', name)
    log.debug( 'data=%s', data)
    log.debug( 'shape=%s' , data.shape)
    log.debug( 'type=%s', data.dtype.char)
    log.debug( 'dims=%s', dims)
    log.debug( 'attrs=%s', attrs)
    return BaseType(name=name, data=data, shape=data.shape, type=data.dtype.char, dimensions=dims, attributes=attrs)



if __name__ == '__main__':
    import sys
    from paste.httpserver import serve

    application = Handler(sys.argv[1])
    serve(application, port=8001)
