import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './api'

interface AppConfig {
  airflow_ui_url: string
  dashboard_refresh_interval_sec: number
  failure_badge_refresh_sec: number
  failure_badge_hours_lookback: number
  pipeline_query_limit: number
  jobs_query_limit: number
  logs_query_limit: number
  app_version: string
  app_release_name: string
  [key: string]: string | number
}

const DEFAULTS: AppConfig = {
  airflow_ui_url: 'http://localhost:8080',
  dashboard_refresh_interval_sec: 60,
  failure_badge_refresh_sec: 300,
  failure_badge_hours_lookback: 24,
  pipeline_query_limit: 20,
  jobs_query_limit: 50,
  logs_query_limit: 30,
  app_version: '1.0',
  app_release_name: '',
}

export function useConfig(): AppConfig {
  const { data } = useQuery<AppConfig>({
    queryKey: ['app-config'],
    queryFn: () => apiFetch('/config'),
    staleTime: 300_000,
  })
  return { ...DEFAULTS, ...(data ?? {}) }
}

export function useAirflowUrl(): string {
  return useConfig().airflow_ui_url
}
