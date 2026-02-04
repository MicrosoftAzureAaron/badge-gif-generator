// Module to create role assignment on storage account from another resource group
// This is needed because the storage account is in the primary resource group
// but the VM identity is in a secondary resource group

param storageAccountName string
param principalId string
param roleDefinitionId string = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // Storage Blob Data Contributor

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageAccountName
}

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, principalId, roleDefinitionId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

output roleAssignmentId string = roleAssignment.id
