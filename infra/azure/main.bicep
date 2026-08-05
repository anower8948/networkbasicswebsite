// ---------------------------------------------------------------------------
// Network Learning Platform — Azure infrastructure.
//
// Two Linux App Services (API and web) in front of a Flexible Server for
// PostgreSQL, with secrets held in Key Vault and read through managed identity
// so no connection string is ever stored in an app setting.
//
//   az deployment group create \
//     --resource-group nlp-prod \
//     --template-file main.bicep \
//     --parameters @main.parameters.json
// ---------------------------------------------------------------------------

@description('Short environment name, used in every resource name.')
@allowed(['dev', 'staging', 'prod'])
param environmentName string = 'prod'

@description('Azure region for every resource.')
param location string = resourceGroup().location

@description('Public hostname the browser reaches, e.g. learn.example.com.')
param frontendHostname string

@description('PostgreSQL administrator login.')
param dbAdminUser string

@description('PostgreSQL administrator password.')
@secure()
param dbAdminPassword string

@description('Container registry that holds the API and web images.')
param registryServer string

@description('Image tag to deploy. Use the commit SHA, never "latest".')
param imageTag string

var prefix = 'nlp-${environmentName}'
var dbName = 'network_learning'

// ---------------------------------------------------------------------------
// Database
// ---------------------------------------------------------------------------
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: '${prefix}-pg'
  location: location
  sku: {
    // B1ms is adequate for a first production deployment; scale up before
    // scaling out, since a single writer is not the bottleneck at this size.
    name: environmentName == 'prod' ? 'Standard_D2ds_v5' : 'Standard_B1ms'
    tier: environmentName == 'prod' ? 'GeneralPurpose' : 'Burstable'
  }
  properties: {
    version: '17'
    administratorLogin: dbAdminUser
    administratorLoginPassword: dbAdminPassword
    storage: {
      storageSizeGB: 32
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: 14
      geoRedundantBackup: environmentName == 'prod' ? 'Enabled' : 'Disabled'
    }
    highAvailability: {
      mode: environmentName == 'prod' ? 'ZoneRedundant' : 'Disabled'
    }
  }

  resource database 'databases' = {
    name: dbName
  }

  // App Service outbound addresses are not fixed, so the platform rule is the
  // practical option here. Tighten to VNet integration + a private endpoint
  // when the deployment justifies it.
  resource allowAzure 'firewallRules' = {
    name: 'AllowAzureServices'
    properties: {
      startIpAddress: '0.0.0.0'
      endIpAddress: '0.0.0.0'
    }
  }
}

// ---------------------------------------------------------------------------
// Secrets
// ---------------------------------------------------------------------------
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${prefix}-kv'
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    // Recovering a vault someone deleted by accident is worth more than the
    // convenience of being able to delete one.
    enablePurgeProtection: true
  }
}

resource secretDatabaseUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'database-url'
  properties: {
    value: 'postgresql+asyncpg://${dbAdminUser}:${dbAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${dbName}?ssl=require'
  }
}

// ---------------------------------------------------------------------------
// Compute
// ---------------------------------------------------------------------------
resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${prefix}-plan'
  location: location
  sku: {
    name: environmentName == 'prod' ? 'P1v3' : 'B1'
  }
  kind: 'linux'
  properties: {
    reserved: true // required for Linux
  }
}

resource api 'Microsoft.Web/sites@2023-12-01' = {
  name: '${prefix}-api'
  location: location
  // System-assigned identity is what lets the app read Key Vault without
  // holding a credential of its own.
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'DOCKER|${registryServer}/nlp-api:${imageTag}'
      alwaysOn: environmentName == 'prod'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      http20Enabled: true
      healthCheckPath: '/api/v1/health'
      appSettings: [
        { name: 'WEBSITES_PORT', value: '8000' }
        { name: 'ENVIRONMENT', value: 'production' }
        { name: 'DEBUG', value: 'false' }
        { name: 'REFRESH_COOKIE_SECURE', value: 'true' }
        { name: 'HSTS_ENABLED', value: 'true' }
        { name: 'RATE_LIMIT_ENABLED', value: 'true' }
        { name: 'FRONTEND_URL', value: 'https://${frontendHostname}' }
        { name: 'CORS_ORIGINS', value: 'https://${frontendHostname}' }
        { name: 'ALLOWED_HOSTS', value: '${prefix}-api.azurewebsites.net,${frontendHostname}' }
        // Bootstrapping an admin by registration is a foothold once the real
        // admin exists, so it is off from the first production boot.
        { name: 'BOOTSTRAP_FIRST_USER_AS_ADMIN', value: 'false' }
        {
          name: 'SECRET_KEY'
          value: '@Microsoft.KeyVault(VaultName=${keyVault.name};SecretName=jwt-secret-key)'
        }
        {
          name: 'DATABASE_URL'
          value: '@Microsoft.KeyVault(VaultName=${keyVault.name};SecretName=database-url)'
        }
      ]
    }
  }
}

resource web 'Microsoft.Web/sites@2023-12-01' = {
  name: '${prefix}-web'
  location: location
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'DOCKER|${registryServer}/nlp-web:${imageTag}'
      alwaysOn: environmentName == 'prod'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      http20Enabled: true
      appSettings: [
        { name: 'WEBSITES_PORT', value: '80' }
      ]
    }
  }
}

// Key Vault Secrets User — read, and nothing more.
var secretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource apiCanReadSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, api.id, secretsUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      secretsUserRoleId
    )
    principalId: api.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output apiHostname string = api.properties.defaultHostName
output webHostname string = web.properties.defaultHostName
output keyVaultName string = keyVault.name
output postgresFqdn string = postgres.properties.fullyQualifiedDomainName
