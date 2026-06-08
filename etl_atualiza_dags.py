from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from airflow.www.app import create_app
from airflow.models import DagModel
from sqlalchemy.orm import Session

def grant_etl_permissions_to_viewer():
    """
    Concede can_read e can_edit no role Viewer
    para todas as DAGs com prefixo 'etl_'.
    """
    from airflow.www.app import create_app
    from flask_appbuilder.security.sqla.models import Role, PermissionView
    from airflow.www.fab_security.sqla.models import Permission, ViewMenu

    flask_app = create_app()

    with flask_app.app_context():
        sm = flask_app.appbuilder.sm
        session: Session = sm.get_session

        # Busca o role Viewer
        viewer_role = sm.find_role("Viewer")
        if not viewer_role:
            raise ValueError("Role 'Viewer' não encontrado.")

        # Busca todas as DAGs com prefixo etl_
        etl_dags = session.query(DagModel).filter(
            DagModel.dag_id.like("etl_%")
        ).all()

        print(f"DAGs encontradas com prefixo 'etl_': {[d.dag_id for d in etl_dags]}")

        actions = ["can_read", "can_edit"]

        for dag in etl_dags:
            resource_name = f"DAG:{dag.dag_id}"

            for action_name in actions:
                # Garante que o recurso existe
                resource = sm.add_view_menu(resource_name)

                # Garante que a permissão existe
                perm = sm.add_permission_view_menu(action_name, resource_name)

                # Adiciona ao role Viewer se ainda não tiver
                if perm not in viewer_role.permissions:
                    sm.add_permission_role(viewer_role, perm)
                    print(f"  ✔ Adicionado: {action_name} on {resource_name}")
                else:
                    print(f"  — Já existe: {action_name} on {resource_name}")

        print("Concluído.")


with DAG(
    dag_id="admin_grant_etl_permissions_to_viewer",
    schedule_interval=None,  # execução manual ou via trigger
    start_date=days_ago(1),
    catchup=False,
    tags=["admin", "segurança", "permissões"],
    description="Concede permissão de execução nas DAGs etl_ ao role Viewer",
) as dag:

    grant_permissions = PythonOperator(
        task_id="grant_etl_permissions_to_viewer",
        python_callable=grant_etl_permissions_to_viewer,
    )
