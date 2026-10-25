try { await import('./test-migration.mjs'); } catch (error) { console.error(error.message); process.exitCode=1; }
