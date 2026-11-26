// A small key-value store on IndexedDB that never fails the caller: on any error it answers from memory.
export interface Store {
  get<T>(key: string): Promise<T | undefined>;
  set(key: string, value: unknown): Promise<void>;
}

export function memoryStore(): Store {
  const map = new Map<string, unknown>();
  return {
    async get<T>(key: string) {
      return map.get(key) as T | undefined;
    },
    async set(key, value) {
      map.set(key, value);
    },
  };
}

const DB_NAME = "the-rebuild";
const KV = "kv";

const done = <T>(request: IDBRequest<T>) =>
  new Promise<T>((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

export async function openStore(idb: IDBFactory | undefined = globalThis.indexedDB): Promise<Store> {
  const memory = memoryStore();
  let db: IDBDatabase | null = null;
  try {
    const request = idb!.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(KV);
    db = await done(request);
  } catch {
    return memory;
  }
  const fail = () => {
    db?.close();
    db = null;
  };
  return {
    async get<T>(key: string) {
      if (db) {
        try {
          const value = await done(db.transaction(KV, "readonly").objectStore(KV).get(key));
          if (value !== undefined) return value as T;
        } catch {
          fail();
        }
      }
      return memory.get<T>(key);
    },
    async set(key, value) {
      await memory.set(key, value);
      if (!db) return;
      try {
        const tx = db.transaction(KV, "readwrite");
        const finished = new Promise<void>((resolve, reject) => {
          tx.oncomplete = () => resolve();
          tx.onerror = () => reject(tx.error);
          tx.onabort = () => reject(tx.error);
        });
        tx.objectStore(KV).put(value, key);
        await finished;
      } catch {
        fail();
      }
    },
  };
}
