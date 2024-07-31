import sys
import json
from statistics import mean

stats_by_category = {}
stats_by_category_times = {}

with open(sys.argv[1]) as f:
    while line := f.readline():
        stats = json.loads(line)

        cat = stats['category']
        if cat not in stats_by_category:
            stats_by_category[cat] = {}

        total = stats['total']

        if cat not in stats_by_category_times:
            stats_by_category_times[cat] = {
                    "sum": total,
                    "times": 1,
            }
        else:
            stats_by_category_times[cat]["sum"] += total
            stats_by_category_times[cat]["times"] += 1

        for k, v in stats['events'].items():
            if k not in stats_by_category[cat]:
                stats_by_category[cat][k] = []
            stats_by_category[cat][k].append(sum(v)/total)

for cat, events in stats_by_category.items():
    mtime = (stats_by_category_times[cat]["sum"]/stats_by_category_times[cat]["times"])/1000_000
    print("==== category:", cat, "==== mean time in ms:", mtime)
    for name, parts in events.items():
        print(f'{name}: {mean(parts)}')
    print()
              
