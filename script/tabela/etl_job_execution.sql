USE [DMDB41]
GO

/****** Object:  Table [dbo].[etl_job_execution]    Script Date: 30/05/2026 00:56:44 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[etl_job_execution](
	[execution_id] [varchar](50) NOT NULL,
	[project] [varchar](100) NOT NULL,
	[job_name] [varchar](200) NOT NULL,
	[pipeline] [varchar](200) NULL,
	[host] [varchar](200) NULL,
	[start_time] [datetime2](7) NOT NULL,
	[end_time] [datetime2](7) NULL,
	[duration_seconds] [int] NULL,
	[status_code] [int] NULL,
	[attempt] [int] NULL,
	[log_file] [varchar](500) NULL,
	[created_at] [datetime2](7) NULL,
	[status] [varchar](20) NULL,
	[updated_at] [datetime2](7) NULL,
	[task_id] [varchar](200) NOT NULL,
 CONSTRAINT [PK_etl_job_execution] PRIMARY KEY CLUSTERED 
(
	[execution_id] ASC,
	[job_name] ASC,
	[task_id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[etl_job_execution] ADD  DEFAULT ((1)) FOR [attempt]
GO

ALTER TABLE [dbo].[etl_job_execution] ADD  DEFAULT (getdate()) FOR [created_at]
GO


