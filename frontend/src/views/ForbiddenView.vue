<template>
  <div class="card mx-auto max-w-lg p-8 text-center">
    <h1 class="text-lg font-semibold">You don't have access to this page</h1>
    <p class="mt-2 text-sm text-slate-600">Your role in this workspace doesn't include it. Ask an owner if you need access.</p>
    <RouterLink :to="{ name: 'dashboard' }" class="mt-4 inline-block text-sm font-medium text-brand-700 hover:underline">Back to today</RouterLink>
  </div>
</template>
