import sys
import json
from statistics import mean

stats_by_category = {}
total_time_by_category = {}
total_logs_by_category = {}

with open(sys.argv[1]) as f:
    while line := f.readline():
        stats = json.loads(line)

        tags = ", ".join(stats['tags'])
        if tags not in stats_by_category:
            stats_by_category[tags] = {}
            total_time_by_category[tags] = 0
            total_logs_by_category[tags] = 0

        total = stats['total']
        total_time_by_category[tags] += total
        total_logs_by_category[tags] += 1
        for k, v in stats['events'].items():
            if k not in stats_by_category[tags]:
                stats_by_category[tags][k] = []
            stats_by_category[tags][k].append(sum(v)/total)

for tags, events in stats_by_category.items():
    mtime = total_time_by_category[tags]/total_logs_by_category[tags]
    count = total_logs_by_category[tags]
    print("==== tags:", tags, "==== mean time:", mtime/1000000, "==== count:", count)
    for name, parts in events.items():
        print(f'{name}: {mean(parts)}')
    print()

