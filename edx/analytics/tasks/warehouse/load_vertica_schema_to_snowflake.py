"""
Tasks to load a Vertica schema from S3 into Snowflake.
"""

from __future__ import absolute_import

import logging
import re

import luigi

from edx.analytics.tasks.common.snowflake_load import SnowflakeLoadDownstreamMixin, SnowflakeLoadFromHiveTSVTask
from edx.analytics.tasks.common.vertica_export import (
    VerticaSchemaExportMixin, VerticaTableExportMixin, VerticaTableFromS3Mixin
)
from edx.analytics.tasks.util.url import ExternalURL

log = logging.getLogger(__name__)


class LoadVerticaTableFromS3ToSnowflakeTask(VerticaTableExportMixin, VerticaTableFromS3Mixin, SnowflakeLoadFromHiveTSVTask):
    """
    Task to load a Vertica table from S3 into Snowflake.
    """

    def snowflake_compliant_schema(self):
        """
        Returns the Snowflake schema in the format (column name, column type) for the indicated table.

        Information about "nullable" or required fields is not included.
        """
        results = []
        for column_name, field_type, _ in self.vertica_table_schema:
            if column_name == 'start' or " " in column_name:
                column_name = '"{}"'.format(column_name)

            if field_type.startswith('long '):
                field_type = field_type.lstrip('long ')
            elif 'numeric(' in field_type:
                # Snowflake only handles numeric precision up to 38. This regex should find either 1 or 2 numbers
                # ex: numeric(52) or numeric(58, 4). First number is precision, second is scale.
                precision_and_scale = re.findall(r'[0-9]+', field_type)
                if int(precision_and_scale[0]) > 38:
                    # If it has scale, try to preserve that
                    if len(precision_and_scale) == 2:
                        field_type = 'numeric(38,{})'.format(precision_and_scale[1])
                    else:
                        field_type = 'numeric(38)'
            elif field_type == 'uuid':
                # Snowflake has no uuid type, but Vertica's is just a 36 character string
                field_type = 'varchar(36)'

            results.append((column_name, field_type))

        return results

    @property
    def insert_source_task(self):
        """
        This assumes we have already exported vertica tables to S3 using SqoopImportFromVertica through VerticaSchemaToS3Task
        workflow, so we specify ExternalURL here.
        """
        return ExternalURL(url=self.s3_location_for_table)

    @property
    def table(self):
        return self.table_name

    @property
    def file_format_name(self):
        return 'vertica_sqoop_export_format'

    @property
    def columns(self):
        return self.snowflake_compliant_schema()

    @property
    def null_marker(self):
        return self.sqoop_null_string

    @property
    def pattern(self):
        return '.*part-m.*'

    @property
    def field_delimiter(self):
        return self.sqoop_fields_terminated_by


class LoadVerticaSchemaFromS3ToSnowflakeTask(VerticaSchemaExportMixin, VerticaTableFromS3Mixin, SnowflakeLoadDownstreamMixin, luigi.WrapperTask):
    """
    A task that loads into Snowflake all the tables in S3 dumped from a Vertica schema.

    Reads all tables in a schema and, if they are not listed in the `exclude` parameter, schedules a
    LoadVerticaTableFromS3ToSnowflake task for each table.
    """

    def requires(self):
        yield ExternalURL(url=self.vertica_credentials)

        for table_name in self.get_table_list_for_schema():
            yield LoadVerticaTableFromS3ToSnowflakeTask(
                date=self.date,
                overwrite=self.overwrite,
                intermediate_warehouse_path=self.intermediate_warehouse_path,
                credentials=self.credentials,
                warehouse=self.warehouse,
                role=self.role,
                sf_database=self.sf_database,
                schema=self.schema,
                scratch_schema=self.scratch_schema,
                run_id=self.run_id,
                table_name=table_name,
                vertica_schema_name=self.vertica_schema_name,
                vertica_warehouse_name=self.vertica_warehouse_name,
                vertica_credentials=self.vertica_credentials,
                sqoop_null_string=self.sqoop_null_string,
                sqoop_fields_terminated_by=self.sqoop_fields_terminated_by,
            )

    def complete(self):
        # OverwriteOutputMixin changes the complete() method behavior, so we override it.
        return all(r.complete() for r in luigi.task.flatten(self.requires()))
