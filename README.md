# 🚀 Django Deployment Pipeline: Bitbucket to AWS ECS Fargate

Este proyecto automatiza el despliegue de una aplicación Django en AWS ECS (Fargate) utilizando Jenkins. La arquitectura implementa infraestructura inmutable, inyección segura de secretos vía AWS SSM Parameter Store y gestión dinámica de balanceadores de carga.

## 📋 Tabla de Contenidos
1. [Arquitectura del Flujo](#-arquitectura-del-flujo)
2. [Estructura del Repositorio](#-estructura-del-repositorio)
3. [Prerrequisitos en AWS](#-prerrequisitos-en-aws)
4. [Configuración del Servidor Jenkins (EC2)](#-configuración-del-servidor-jenkins-ec2)
5. [Configuración del Pipeline](#-configuración-del-pipeline)
6. [Detalles Técnicos](#-detalles-técnicos)

---

## 🏗 Arquitectura del Flujo

El flujo sigue una estrategia de **CI/CD Declarativo** donde Jenkins orquesta la construcción de Docker y un script de Python (\`deploy.py\`) maneja la lógica de negocio de la infraestructura AWS.

\`\`\`mermaid
flowchart TD
    Start((Push Bitbucket)) --> Jenkins[Jenkins CI\n(EC2)]
    
    subgraph Build_Stage
        Jenkins -->|Docker Build| Image[Imagen Django]
        Image -->|Push| ECR[AWS ECR]
    end
    
    subgraph Deploy_Stage
        Jenkins -->|Ejecuta| PyScript[deploy.py]
        PyScript -->|Lee config| EnvFile[env.yml]
        
        PyScript -->|Check/Create| TG[Target Group]
        PyScript -->|Map Variables| SSM[AWS SSM Parameter Store]
        
        PyScript -->|Register| TaskDef[Task Definition]
        SSM -.->|Ref Secretos| TaskDef
        
        PyScript -->|Update/Create| Service[ECS Service]
    end
    
    Service -->|Despliega| Fargate[Contenedores Fargate]
    ALB[Load Balancer] --> TG
    TG --> Fargate
\`\`\`

---

## 📂 Estructura del Repositorio

Archivos clave para el funcionamiento del pipeline:

| Archivo | Descripción |
| :--- | :--- |
| **\`Jenkinsfile\`** | Definición del Pipeline. Contiene los stages (Checkout, Build, Push, Deploy). |
| **\`deploy.py\`** | Script de orquestación en Python (Boto3). Gestiona Target Groups, Task Definitions y Servicios ECS. |
| **\`env.yml\`** | Mapa de variables de entorno. Asocia nombres de variables en Django con rutas en AWS SSM. |
| **\`Dockerfile\`** | Instrucciones para construir la imagen de la aplicación Django. |
| **\`docker-compose.yml\`** | Configuración para levantar el servidor Jenkins en la EC2. |
| **\`jenkins-setup/\`** | Carpeta recomendada para guardar los archivos de configuración de Jenkins (\`Dockerfile\`, \`plugins.txt\`, \`default-user.groovy\`). |

---

## ☁ Prerrequisitos en AWS

Antes de ejecutar el primer despliegue, asegúrate de tener los siguientes recursos:

1.  **Red:** Una VPC con Subnets (públicas o privadas con NAT) y un Security Group para la app (Puerto 8000).
2.  **Cluster ECS:** Un cluster creado (puede estar vacío). Ejemplo: \`mi-cluster-ecs\`.
3.  **ECR:** Un repositorio para las imágenes. Ejemplo: \`mi-django-app\`.
4.  **IAM Role para Jenkins:** La instancia EC2 debe tener un rol con permisos:
    * \`AmazonEC2ContainerRegistryPowerUser\`
    * \`AmazonSSMReadOnlyAccess\`
    * \`AmazonECS_FullAccess\`
    * \`ElasticLoadBalancingFullAccess\`
5.  **Parameter Store:** Las variables sensibles deben estar creadas en AWS SSM.

---

## 🛠 Configuración del Servidor Jenkins (EC2)

Para levantar el servidor CI/CD con todas las dependencias (Docker, AWS CLI v2, Python Boto3) preinstaladas:

1.  Conéctate por SSH a tu EC2.
2.  Crea un archivo \`.env\` para proteger tus credenciales:
    \`\`\`bash
    JENKINS_ADMIN_USER=admin_infra
    JENKINS_ADMIN_PASSWORD=TuPasswordSuperSeguro!
    \`\`\`
3.  Ejecuta el entorno con Docker Compose:
    \`\`\`bash
    docker-compose up -d --build
    \`\`\`
4.  **Resultado:** Jenkins estará disponible en el puerto \`8080\`.
    * *Plugins:* Se instalan automáticamente (\`plugins.txt\`).
    * *Usuario:* Se crea automáticamente (\`default-user.groovy\`).
    * *Docker:* El contenedor usa el motor Docker del host (DooD).

---

## 🚀 Configuración del Pipeline

1.  **En Jenkins:**
    * Crear "New Item" -> Tipo "Pipeline".
    * Definition: **Pipeline script from SCM**.
    * SCM: **Git**.
    * Repository URL: \`https://bitbucket.org/usuario/repo.git\`.
    * Credentials: Usa un **App Password** de Bitbucket.
    * Script Path: \`Jenkinsfile\`.

2.  **En Bitbucket (Webhook):**
    * Ir a Repository Settings -> Webhooks.
    * URL: \`http://<IP-EC2>:8080/bitbucket-hook/\`
    * Trigger: Repository Push.

---

## ⚙ Detalles Técnicos

### Inyección de Secretos (\`env.yml\`)
El archivo \`env.yml\` no contiene contraseñas reales, solo referencias. Esto mantiene el repositorio seguro.

\`\`\`yaml
variables:
  DB_PASSWORD: /prod/django/db_password
  SECRET_KEY: /prod/django/secret_key
\`\`\`
El script \`deploy.py\` convierte estas referencias en una configuración \`valueFrom\` compatible con ECS, haciendo que los contenedores lean el secreto directamente de AWS al arrancar.

### Script de Orquestación (\`deploy.py\`)
Este script es **idempotente**:
* Verifica si el Target Group existe; si no, lo crea.
* Verifica si el Servicio ECS existe; si no, lo crea. Si existe, fuerza un \`new-deployment\`.
* Gestiona automáticamente el registro de nuevas revisiones de Task Definition.
