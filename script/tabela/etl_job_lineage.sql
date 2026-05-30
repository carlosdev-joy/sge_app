USE [DMDB41]
GO

/****** Object:  Table [dbo].[etl_job_lineage]    Script Date: 30/05/2026 00:56:15 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[etl_job_lineage](
	[id] [int] IDENTITY(1,1) NOT NULL,
	[pipeline_name] [nvarchar](200) NOT NULL,
	[job_name] [nvarchar](200) NOT NULL,
	[direction] [nvarchar](10) NOT NULL,
	[object_type] [nvarchar](20) NOT NULL,
	[object_name] [nvarchar](500) NOT NULL,
	[created_at] [datetime2](7) NOT NULL,
	[updated_at] [datetime2](7) NOT NULL,
 CONSTRAINT [PK_etl_job_lineage] PRIMARY KEY CLUSTERED 
(
	[id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[etl_job_lineage] ADD  DEFAULT (sysdatetime()) FOR [created_at]
GO

ALTER TABLE [dbo].[etl_job_lineage] ADD  DEFAULT (sysdatetime()) FOR [updated_at]
GO

ALTER TABLE [dbo].[etl_job_lineage]  WITH CHECK ADD  CONSTRAINT [FK_etl_job_lineage_job] FOREIGN KEY([pipeline_name], [job_name])
REFERENCES [dbo].[etl_pipeline_job] ([pipeline_name], [job_name])
GO

ALTER TABLE [dbo].[etl_job_lineage] CHECK CONSTRAINT [FK_etl_job_lineage_job]
GO


