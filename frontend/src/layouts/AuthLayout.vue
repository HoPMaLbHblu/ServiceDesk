<template>
  <div class="flex min-h-full flex-col items-center justify-center px-4 py-10">
    <RouterLink to="/" class="mb-6 flex items-center gap-2 text-xl font-semibold text-slate-900">
      <img src="/favicon.svg" alt="" class="h-8 w-8" />
      ServiceDesk
    </RouterLink>
    <main class="w-full max-w-md">
      <RouterView />
    </main>
  </div>
</template>
