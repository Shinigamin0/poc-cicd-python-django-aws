import boto3
import argparse
import sys
import yaml
import time

# --- CONFIGURACIÓN INICIAL ---
# Inicializamos los clientes de AWS. 
# Boto3 tomará las credenciales automáticamente del Rol IAM de la EC2 Jenkins.
elbv2 = boto3.client('elbv2')
ecs = boto3.client('ecs')
ssm = boto3.client('ssm')
sts = boto3.client('sts')

def get_account_id():
    """Obtiene el ID de la cuenta AWS actual"""
    return sts.get_caller_identity()['Account']

def get_ssm_parameter_arn(param_name):
    """
    Convierte un nombre de parámetro (ej: /prod/db_pass) en su ARN completo.
    Esto es necesario para que ECS pueda leer el secreto de forma segura.
    """
    try:
        # Solo verificamos que exista, no traemos el valor (seguridad)
        ssm.get_parameter(Name=param_name)
        region = boto3.session.Session().region_name
        account_id = get_account_id()
        # Construcción manual del ARN para evitar llamadas extra
        return f"arn:aws:ssm:{region}:{account_id}:parameter{param_name}"
    except ssm.exceptions.ParameterNotFound:
        print(f"❌ Error Crítico: El parámetro '{param_name}' definido en env.yml NO existe en AWS Parameter Store.")
        sys.exit(1)

def get_or_create_target_group(vpc_id, project_name, port=8000):
    """
    Busca si existe un Target Group para el proyecto. Si no, lo crea.
    """
    tg_name = f"{project_name}-tg"
    
    try:
        response = elbv2.describe_target_groups(Names=[tg_name])
        print(f"✅ Target Group existente encontrado: {tg_name}")
        return response['TargetGroups'][0]['TargetGroupArn']
    except elbv2.exceptions.TargetGroupNotFoundException:
        print(f"⚠️ Target Group '{tg_name}' no existe. Creando uno nuevo...")

    # Creación del Target Group
    response = elbv2.create_target_group(
        Name=tg_name,
        Protocol='HTTP',
        Port=port,
        VpcId=vpc_id,
        TargetType='ip', # Obligatorio para Fargate en modo awsvpc
        HealthCheckProtocol='HTTP',
        HealthCheckPath='/', # Ajusta esto si tu app requiere /health/
        Matcher={'HttpCode': '200-299'}
    )
    return response['TargetGroups'][0]['TargetGroupArn']

def register_task_definition(image_uri, project_name, execution_role_arn, env_vars_map):
    """
    Crea una nueva revisión de la Task Definition con la nueva imagen y secretos.
    """
    print("🔄 Generando configuración de secretos...")
    secrets_config = []
    
    # Mapeo de env.yml a secretos de ECS
    for env_var_name, ssm_path in env_vars_map.items():
        arn = get_ssm_parameter_arn(ssm_path)
        secrets_config.append({
            'name': env_var_name,
            'valueFrom': arn
        })

    print(f"📝 Registrando nueva Task Definition para: {project_name}")
    
    response = ecs.register_task_definition(
        family=project_name,
        networkMode='awsvpc',
        requiresCompatibilities=['FARGATE'],
        cpu='256',    # 0.25 vCPU (Ajustar según necesidad)
        memory='512', # 512 MB RAM (Ajustar según necesidad)
        executionRoleArn=execution_role_arn,
        taskRoleArn=execution_role_arn, # Usamos el mismo rol por simplicidad
        containerDefinitions=[
            {
                'name': f"{project_name}-container",
                'image': image_uri,
                'essential': True,
                'portMappings': [{'containerPort': 8000, 'protocol': 'tcp'}],
                'secrets': secrets_config, # Aquí se inyectan las variables
                'logConfiguration': {
                    'logDriver': 'awslogs',
                    'options': {
                        'awslogs-group': f"/ecs/{project_name}",
                        'awslogs-region': boto3.session.Session().region_name,
                        'awslogs-stream-prefix': "ecs"
                    }
                }
            }
        ]
    )
    return response['taskDefinition']['taskDefinitionArn']

def deploy_service(cluster_name, service_name, task_def_arn, tg_arn, subnets, security_groups):
    """
    Crea el servicio si no existe, o lo actualiza si ya existe.
    """
    print(f"🚀 Iniciando despliegue del servicio: {service_name}")
    
    # Verificar existencia del servicio
    service_exists = True
    try:
        ecs.describe_services(cluster=cluster_name, services=[service_name])['services'][0]['serviceArn']
    except (IndexError, KeyError):
        service_exists = False
        # Nota: describe_services no lanza excepción si no existe, devuelve lista vacía o estado INACTIVE.
        # Una comprobación más robusta es iterar sobre la respuesta, pero esto sirve para el ejemplo.

    # Verificación robusta: si la lista 'services' tiene elementos y status es ACTIVE
    response = ecs.describe_services(cluster=cluster_name, services=[service_name])
    if not response['services'] or response['services'][0]['status'] == 'INACTIVE':
        service_exists = False

    if service_exists:
        print("🔄 El servicio existe. Ejecutando Update (Rolling Deployment)...")
        ecs.update_service(
            cluster=cluster_name,
            service=service_name,
            taskDefinition=task_def_arn,
            forceNewDeployment=True # Fuerza a bajar contenedores viejos y subir nuevos
        )
    else:
        print("✨ El servicio NO existe. Creando servicio nuevo...")
        ecs.create_service(
            cluster=cluster_name,
            serviceName=service_name,
            taskDefinition=task_def_arn,
            launchType='FARGATE',
            desiredCount=1,
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': subnets,
                    'securityGroups': security_groups,
                    'assignPublicIp': 'ENABLED' # Cambiar a DISABLED si usas subnets privadas con NAT Gateway
                }
            },
            loadBalancers=[
                {
                    'targetGroupArn': tg_arn,
                    'containerName': f"{service_name.replace('-service', '')}-container", # Debe coincidir con containerDefinition
                    'containerPort': 8000
                }
            ]
        )
    print("✅ Orden de despliegue enviada a ECS exitosamente.")

# --- BLOQUE PRINCIPAL ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Script de Despliegue ECS Fargate')
    
    # Argumentos obligatorios que vienen del Jenkinsfile
    parser.add_argument('--image', required=True, help='URI de la imagen en ECR')
    parser.add_argument('--env-yml', required=True, help='Ruta al archivo env.yml')
    parser.add_argument('--vpc-id', required=True, help='ID de la VPC')
    parser.add_argument('--cluster', required=True, help='Nombre del Cluster ECS')
    parser.add_argument('--project', required=True, help='Nombre del proyecto (usado para prefijos)')
    parser.add_argument('--subnets', required=True, help='Lista de subnets separadas por coma')
    parser.add_argument('--security-groups', required=True, help='Lista de security groups separados por coma')

    args = parser.parse_args()

    print(f"--- 🏁 Iniciando Script de Despliegue: {args.project} ---")

    # 1. Cargar configuración de variables
    try:
        with open(args.env_yml) as f:
            # Asume estructura: { variables: { KEY: /path/ssm } }
            env_map = yaml.safe_load(f)['variables']
    except Exception as e:
        print(f"❌ Error leyendo {args.env_yml}: {e}")
        sys.exit(1)

    # 2. Obtener/Crear Target Group
    tg_arn = get_or_create_target_group(args.vpc_id, args.project)

    # 3. Definir Rol de Ejecución (Usamos el estándar de AWS ecsTaskExecutionRole)
    # Asegúrate de que este rol exista en tu cuenta IAM
    account_id = get_account_id()
    exec_role_arn = f"arn:aws:iam::{account_id}:role/ecsTaskExecutionRole"

    # 4. Registrar Task Definition
    td_arn = register_task_definition(
        image_uri=args.image,
        project_name=args.project,
        execution_role_arn=exec_role_arn,
        env_vars_map=env_map
    )

    # 5. Desplegar Servicio (Convertimos strings "sub1,sub2" a listas ["sub1", "sub2"])
    deploy_service(
        cluster_name=args.cluster,
        service_name=f"{args.project}-service",
        task_def_arn=td_arn,
        tg_arn=tg_arn,
        subnets=args.subnets.split(','),
        security_groups=args.security_groups.split(',')
    )

    print("--- 🏁 Despliegue finalizado. Monitorea el cluster en la consola AWS ---")