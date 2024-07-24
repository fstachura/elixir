import sys
import json
from statistics import mean

stats_by_category = {}

with open(sys.argv[1]) as f:
    while line := f.readline():
        stats = json.loads(line)

        cat = stats['category']
        if cat not in stats_by_category:
            stats_by_category[cat] = {}

        total = stats['total']
        for k, v in stats['events'].items():
            if k not in stats_by_category[cat]:
                stats_by_category[cat][k] = []
            stats_by_category[cat][k].append(sum(v)/total)

for cat, events in stats_by_category.items():
    print("==== category:", cat)
    for name, parts in events.items():
        print(f'{name}: {mean(parts)}')
    print()
              
