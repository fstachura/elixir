import re
from dataclasses import dataclass
from typing import List, Union, Tuple, Dict, Any

from .filters.utils import Filter, FilterContext
from .filters import default_filters
from .projects import projects

@dataclass
class ProjectConfig:
    filters: List[Union[Filter, Tuple[Filter, Dict[str, Any]]]]


# Returns a list of applicable filters for project_name under provided filter context
def get_filters(ctx: FilterContext, project: ProjectConfig) -> List[Filter]:
    filter_classes = project.filters
    filters = []

    for filter_cls in filter_classes:
        if type(filter_cls) == tuple and len(filter_cls) == 2:
            cls, kwargs = filter_cls
            filters.append(cls(**kwargs))
        elif type(filter_cls) == type:
            filters.append(filter_cls())
        else:
            raise ValueError(f"Invalid filter: {filter_cls}, " \
                    "should be either a two element tuple or a type. " \
                    "Make sure projects[project]['filter'] in project.py is valid.")

    return [f for f in filters if f.check_if_applies(ctx)]

