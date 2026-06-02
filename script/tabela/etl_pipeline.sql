USE [DMDB41]
GO

/****** Object:  Table [dbo].[etl_pipeline]    Script Date: 30/05/2026 00:55:45 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[etl_pipeline](
	[pipeline_name] [nvarchar](200) NOT NULL,
	[scheduled_time] [time](0) NOT NULL,
	[schedule_type] [varchar](20) NULL, -- hourly | daily | weekly | monthly
	[schedule_hour] [tinyint] NULL, -- 0-23
	[schedule_minute] [tinyint] NULL, -- 0-59
	[schedule_dow] [tinyint] NULL, -- 0=Dom .. 6=Sab
	[schedule_dom] [tinyint] NULL, -- 1-31
	[active] [bit] NULL,
	[last_execution] [datetime2](0) NULL,
	[created_at] [datetime2](0) NULL,
	[updated_at] [datetime2](0) NULL,
	[ENVIA_MSG_INICIO] [bit] NOT NULL,
	[ENVIA_MSG_FIM] [bit] NOT NULL,
	[ENVIA_MSG_ERRO] [bit] NOT NULL,
	[DAG_CRIADA] [bit] NOT NULL,
	[project_name] [nvarchar](50) NOT NULL,
	[domain] [nvarchar](100) NOT NULL,
	[tags] [nvarchar](500) NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[pipeline_name] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[etl_pipeline] ADD  DEFAULT ((1)) FOR [active]
GO

ALTER TABLE [dbo].[etl_pipeline] ADD  DEFAULT (sysdatetime()) FOR [created_at]
GO

ALTER TABLE [dbo].[etl_pipeline] ADD  DEFAULT (sysdatetime()) FOR [updated_at]
GO

ALTER TABLE [dbo].[etl_pipeline] ADD  CONSTRAINT [DF_etl_pipeline_ENVIA_MSG_INICIO]  DEFAULT ((1)) FOR [ENVIA_MSG_INICIO]
GO

ALTER TABLE [dbo].[etl_pipeline] ADD  CONSTRAINT [DF_etl_pipeline_ENVIA_MSG_FIM]  DEFAULT ((1)) FOR [ENVIA_MSG_FIM]
GO

ALTER TABLE [dbo].[etl_pipeline] ADD  CONSTRAINT [DF_etl_pipeline_ENVIA_MSG_ERRO]  DEFAULT ((1)) FOR [ENVIA_MSG_ERRO]
GO

ALTER TABLE [dbo].[etl_pipeline] ADD  CONSTRAINT [DF_etl_pipeline_DAG_CRIADA]  DEFAULT ((0)) FOR [DAG_CRIADA]
GO


