from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import DagBag
from airflow.utils.dates import days_ago

from airflow.www.app import create_app

ROLE_NAME = "Viewer"
PREFIX = "etl_"

def sync_dag_permissions():
    app = create_app()
    with app.app_context():
        sm = app.appbuilder.sm

        # pegar role
        role = sm.find_role(ROLE_NAME)
        if not role:
            raise Exception(f"Role {ROLE_NAME} não encontrado")

        dag_bag = DagBag()
        dags = dag_bag.dags.keys()

        for dag_id in dags:
            if not dag_id.startswith(PREFIX):
                continue

            resource_name = f"DAG:{dag_id}"

            # garantir permissões necessárias
            for action in ["can_read", "can_dag_trigger"]:
                perm = sm.find_permission(action, resource_name)

                if not perm:
                    perm = sm.add_permission_view_menu(action, resource_name)

                if perm not in role.permissions:
                    sm.add_permission_role(role, perm)
                    print(f"Adicionada {action} em {resource_name} ao role {ROLE_NAME}")

default_args = {
    "owner": "airflow",
}

with DAG(
    dag_id="sync_etl_permissions",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=days_ago(1),
    catchup=False,
) as dag:

    sync_permissions = PythonOperator(
        task_id="sync_permissions",
        python_callable=sync_dag_permissions
    )