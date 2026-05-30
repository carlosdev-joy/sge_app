USE [DMDB41]
GO

/****** Object:  Table [dbo].[etl_pipeline_job]    Script Date: 30/05/2026 00:54:08 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[etl_pipeline_job](
	[pipeline_name] [nvarchar](200) NOT NULL,
	[job_name] [nvarchar](200) NOT NULL,
	[execution_order] [int] NOT NULL,
	[created_at] [datetime] NOT NULL,
	[updated_at] [datetime] NULL,
	[job_type] [nvarchar](20) NOT NULL,
	[job_command] [nvarchar](500) NULL,
 CONSTRAINT [PK_etl_pipeline_job] PRIMARY KEY CLUSTERED 
(
	[pipeline_name] ASC,
	[job_name] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[etl_pipeline_job] ADD  DEFAULT (getdate()) FOR [created_at]
GO

ALTER TABLE [dbo].[etl_pipeline_job]  WITH CHECK ADD  CONSTRAINT [FK_pipeline] FOREIGN KEY([pipeline_name])
REFERENCES [dbo].[etl_pipeline] ([pipeline_name])
GO

ALTER TABLE [dbo].[etl_pipeline_job] CHECK CONSTRAINT [FK_pipeline]
GO


