import jenkins.model.*
import hudson.security.*

def env = System.getenv()
def adminUsername = env['JENKINS_ADMIN_USER'] ?: 'admin'
def adminPassword = env['JENKINS_ADMIN_PASSWORD'] ?: 'admin'

def instance = Jenkins.getInstance()

def hudsonRealm = new HudsonPrivateSecurityRealm(false)
def users = hudsonRealm.getAllUsers()

if (!users.find { it.id == adminUsername }) {
    println "--> Iniciando configuración de seguridad..."
    println "--> Creando usuario admin: ${adminUsername}"

    hudsonRealm.createAccount(adminUsername, adminPassword)
    instance.setSecurityRealm(hudsonRealm)

    def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
    strategy.setAllowAnonymousRead(false)
    instance.setAuthorizationStrategy(strategy)

    instance.save()
    println "--> Seguridad configurada exitosamente."
} else {
    println "--> El usuario ${adminUsername} ya existe. Omitiendo creación."
}