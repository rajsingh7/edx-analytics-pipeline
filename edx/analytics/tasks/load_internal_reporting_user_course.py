"""
Loads the user_course table into the warehouse through the pipeline via Hive.

"""
from edx.analytics.tasks.vertica_load import VerticaCopyTask
from edx.analytics.tasks.enrollments import CourseEnrollmentTask
import luigi
from edx.analytics.tasks.util.hive import WarehouseMixin, HivePartition
from edx.analytics.tasks.url import url_path_join, get_target_from_url


class LoadInternalReportingUserCourseToWarehouse(WarehouseMixin, VerticaCopyTask):

    interval = luigi.DateIntervalParameter()
    n_reduce_tasks = luigi.Parameter()

    @property
    def partition(self):
        """The table is partitioned by date."""
        return HivePartition('dt', self.interval.date_b.isoformat())  # pylint: disable=no-member

    @property
    def insert_source_task(self):
        self.table = "course_enrollment"
        self.table_location=url_path_join(self.warehouse_path, self.table) + '/'
        partition_location=url_path_join(self.table_location, self.partition.path_spec + '/')

        return (
            get_target_from_url(partition_location)
            # CourseEnrollmentTask(
            #     n_reduce_tasks = self.n_reduce_tasks,
            #     interval = self.interval,
            #     output_root = url_path_join(self.warehouse_path, 'course_enrollment/'),
            #     #overwrite = self.overwrite
            # )
        )

    @property
    def table(self):
        return 'f_user_course'

    @property
    def columns(self):
        """The schema has enrollment_is_active as well, but 'course_enrollment' hive table does not have it."""
        return [
            ('date', 'DATE'),
            ('course_id', 'VARCHAR(200)'),
            ('user_id', 'INTEGER'),
            ('enrollment_is_active', 'INTEGER'),
            ('enrollment_change', 'INTEGER'),
            ('enrollment_mode', 'VARCHAR(100)')
        ]

    @property
    def auto_primary_key(self):
        """Use 'record_number' as primary key to match the schema"""
        return ('record_number', 'AUTO_INCREMENT')

    @property
    def default_columns(self):
        return None
