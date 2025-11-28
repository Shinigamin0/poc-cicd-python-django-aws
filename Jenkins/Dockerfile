FROM jenkins/jenkins:lts-jdk21

# Cambiamos a root para instalaciones del sistema
USER root

# 1. Instalar dependencias base, Python y herramientas de red
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    lsb-release \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 2. Instalar Docker CLI (Versión Oficial Reciente)
# Usamos el repo oficial porque 'docker.io' de apt suele ser viejo
RUN curl -fsSLo /usr/share/keyrings/docker-archive-keyring.asc \
  https://download.docker.com/linux/debian/gpg
RUN echo "deb [arch=$(dpkg --print-architecture) \
  signed-by=/usr/share/keyrings/docker-archive-keyring.asc] \
  https://download.docker.com/linux/debian \
  $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
RUN apt-get update && apt-get install -y docker-ce-cli

# 3. Instalar AWS CLI v2 (Mejor que apt-get install awscli)
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && rm -rf aws awscliv2.zip

# 4. Instalar librerías Python (Boto3 y PyYAML)
# Usamos --break-system-packages para compatibilidad con Debian 12
RUN pip3 install boto3 pyyaml requests --break-system-packages

# 5. Agregar usuario jenkins al grupo docker (Del código que trajiste)
RUN groupadd -f docker && usermod -aG docker jenkins

# 6. INSTALACIÓN AUTOMÁTICA DE PLUGINS (La joya que trajiste)
# Primero copiamos la lista
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
# Ejecutamos el script instalador nativo de Jenkins (corrigiendo propiedad)
RUN jenkins-plugin-cli -f /usr/share/jenkins/ref/plugins.txt

# Volvemos al usuario jenkins
USER jenkins

