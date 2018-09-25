import math

from django.core.management.base import BaseCommand

from contentcuration.perftools import objective


class Command(BaseCommand):

    help = 'Runs db tests and reports the performance results. (Usage: test_server_perf [num_objects=100])'

    def add_arguments(self, parser):
        parser.add_argument('--num-levels', type=int, default=5)
        parser.add_argument('--children-per-level', type=int, default=5)
        parser.add_argument('--num-runs', type=int, default=10)

        parser.add_argument('--stress-test', action='store_true', default=False)

    def handle(self, *args, **options):
        objects = None
        try:
            objects = objective.Objective()

            stats = {}
            num_levels = options['num_levels']
            num_children = options['children_per_level']
            num_objects = num_levels ** num_children
            num_runs = options['num_runs']
            object_types = ['ContentNode', 'File']
            for object_type in object_types:
                stats[object_type] = objects.get_object_creation_stats(object_type, num_objects, num_runs)

            stats['ContentNode-mptt-delay'] = objects.get_object_creation_stats_mptt_delay(num_objects, num_runs)
            stats['ContentNode-treeless'] = objects.get_object_creation_stats_treeless(num_objects, num_runs)

            print("Creating {} nodes for MP tree test".format(num_levels**num_children))
            stats['MP tree'] = objects.get_mptree_creation_stats(num_levels, num_children, num_runs=num_runs)

            print()
            print("Test results:")
            for object_type in stats:
                run_stats = stats[object_type]
                print("Stats for creating {} {} over {} runs: {}".format(num_objects, object_type, num_runs, run_stats))

            if options['stress_test']:
                print("Running stress test simulating creation / cloning of a channel like KA, this will take at least several minutes. Please do not interrupt if possible!")
                stats = objects.get_large_channel_creation_stats()
                for stat in stats:
                    print("{}: {}".format(stat, stats[stat]))

        finally:
            if objects:
                objects.cleanup()
