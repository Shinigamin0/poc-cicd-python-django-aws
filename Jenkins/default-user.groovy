/**
 * Script de inicialización de Jenkins (Versión Blindada)
 * -----------------------------------------------------
 * - Crea el usuario administrador solo si NO existe.
 * - Idempotente: Se puede ejecutar en cada reinicio sin errores.
 * - Seguro: Respeta configuraciones externas (LDAP, AD, OIDC) si se detectan.
 */

import jenkins.model.*
import hudson.security.*

// 1. Obtener credenciales de variables de entorno (seguridad primero)
def env = System.getenv()
def adminUsername = env['JENKINS_ADMIN_USER'] ?: 'admin'
def adminPassword = env['JENKINS_ADMIN_PASSWORD'] ?: 'admin'

println "\n=== [INIT GROOVY] Iniciando configuración de seguridad ==="

def instance = Jenkins.get()
def securityRealm = instance.getSecurityRealm()
def userExists = false
def canConfigure = false

// 2. Evaluar el estado actual de la seguridad
// ---------------------------------------------------------------------

if (securityRealm instanceof HudsonPrivateSecurityRealm) {
    // CASO A: Jenkins ya usa su base de datos local (Escenario normal)
    println "--> Detectado HudsonPrivateSecurityRealm (Base de datos local)."

    // Verificamos si el admin ya existe para no sobrescribirlo
    if (securityRealm.getAllUsers().find { it.id == adminUsername }) {
        println "--> El usuario '${adminUsername}' ya existe. No se requieren cambios."
        userExists = true
    } else {
        canConfigure = true
    }

} else if (securityRealm == SecurityRealm.NO_AUTHENTICATION || securityRealm instanceof hudson.security.LegacySecurityRealm) {
    // CASO B: Jenkins está "virgen" o inseguro. Debemos inicializarlo.
    println "--> Jenkins está inseguro/nuevo. Inicializando HudsonPrivateSecurityRealm..."

    securityRealm = new HudsonPrivateSecurityRealm(false)
    instance.setSecurityRealm(securityRealm)
    instance.save() // Guardado parcial crítico
    canConfigure = true

} else {
    // CASO C: Jenkins usa LDAP, AD, SAML, etc. (Escenario futuro)
    println "--> ⚠️ ALERTA: Se detectó un sistema de seguridad externo: ${securityRealm.getClass().name}"
    println "--> El script omitirá la creación de usuarios locales para evitar conflictos."
    userExists = true // Forzamos esto para saltar el bloque de creación
}

// 3. Crear usuario y definir reglas (Solo si es seguro hacerlo)
// ---------------------------------------------------------------------

if (canConfigure && !userExists) {
    println "--> Creando usuario administrador: ${adminUsername}"

    // Crear la cuenta
    securityRealm.createAccount(adminUsername, adminPassword)

    // Configurar la estrategia: "Logueado manda, Anónimo no ve nada"
    // Solo tocamos esto si estamos en el escenario de base de datos local
    println "--> Configurando estrategia de autorización (FullControlOnceLoggedIn)..."
    def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
    strategy.setAllowAnonymousRead(false)
    instance.setAuthorizationStrategy(strategy)

    instance.save()
    println "--> ✅ Seguridad configurada exitosamente."
}

println "=== [INIT GROOVY] Finalizado ===\n"
