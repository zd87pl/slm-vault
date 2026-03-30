import { fileURLToPath } from "node:url";
import path from "node:path";
import { spawn } from "node:child_process";
import fs from "node:fs";

const DEFAULT_TIMEOUT_MS = 120000;

function findRepoRoot(startDir = path.dirname(fileURLToPath(import.meta.url))) {
  let current = path.resolve(startDir);
  for (let i = 0; i < 6; i += 1) {
    if (fs.existsSync(path.join(current, "advanced_vault")) && fs.existsSync(path.join(current, "pyproject.toml"))) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      break;
    }
    current = parent;
  }
  return path.resolve(startDir, "..", "..", "..");
}

function normalizeConfig(raw = {}) {
  return {
    repoRoot: raw.repoRoot || findRepoRoot(),
    vaultPath: raw.vaultPath || "~/.vault",
    profileName: raw.profileName || "openclaw",
    pythonBin: raw.pythonBin || "python3",
    timeoutMs: Number.isFinite(raw.timeoutMs) ? raw.timeoutMs : DEFAULT_TIMEOUT_MS,
    maxIngestFiles: Number.isFinite(raw.maxIngestFiles) ? raw.maxIngestFiles : 2000
  };
}

function runBridge(command, args = [], config = {}) {
  const resolved = normalizeConfig(config);
  const bridgePath = path.join(resolved.repoRoot, "integrations", "openclaw-enclave", "scripts", "enclave_bridge.py");

  return new Promise((resolve, reject) => {
    const child = spawn(resolved.pythonBin, [bridgePath, command, ...args], {
      cwd: resolved.repoRoot,
      env: {
        ...process.env,
        ENCLAVE_VAULT_PATH: resolved.vaultPath,
        ENCLAVE_PROFILE_NAME: resolved.profileName,
        PYTHONUNBUFFERED: "1"
      },
      stdio: ["ignore", "pipe", "pipe"]
    });

    let stdout = "";
    let stderr = "";

    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error(`Enclave bridge timed out after ${resolved.timeoutMs}ms`));
    }, resolved.timeoutMs);

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });

    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });

    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error(stderr.trim() || `Bridge exited with code ${code}`));
        return;
      }

      const trimmed = stdout.trim();
      try {
        resolve(trimmed ? JSON.parse(trimmed) : {});
      } catch (error) {
        reject(new Error(`Invalid JSON from bridge: ${error.message}\n${trimmed}`));
      }
    });
  });
}

function toolSpec(name, description, inputSchema, handler) {
  return { name, description, inputSchema, handler };
}

function registerTool(api, spec) {
  if (!api || typeof api.registerTool !== "function") {
    throw new Error("OpenClaw API object does not expose registerTool()");
  }

  const attempts = [
    () => api.registerTool(spec),
    () => api.registerTool({
      name: spec.name,
      description: spec.description,
      inputSchema: spec.inputSchema,
      handler: spec.handler
    }),
    () => api.registerTool(spec.name, spec.inputSchema, spec.handler),
    () => api.registerTool(spec.name, spec.description, spec.inputSchema, spec.handler)
  ];

  let lastError = null;
  for (const attempt of attempts) {
    try {
      return attempt();
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error(`Failed to register tool ${spec.name}`);
}

export const enclavePluginManifest = {
  id: "openclaw-enclave",
  name: "Enclave Private Data Layer",
  version: "0.1.0",
  kind: "tool",
  tools: [
    "enclave.status",
    "enclave.ingest",
    "enclave.chat",
    "enclave.scan",
    "enclave.protect",
    "enclave.read",
    "enclave.adapters"
  ]
};

function withProfileArgs(profile, config) {
  const selectedProfile = profile || config.profileName;
  return selectedProfile ? ["--profile-name", selectedProfile] : [];
}

export function registerWithApi(api, rawConfig = {}) {
  const config = normalizeConfig(rawConfig);

  const tools = [
    toolSpec(
      "enclave.status",
      "Show local Enclave, Sheriff, and WDVA readiness.",
      {
        type: "object",
        properties: {
          profile: {
            type: "string",
            description: "Optional private-model profile override."
          }
        }
      },
      async ({ profile } = {}) =>
        runBridge("status", withProfileArgs(profile, config), config)
    ),
    toolSpec(
      "enclave.ingest",
      "Ingest local files or folders into the encrypted local context index.",
      {
        type: "object",
        properties: {
          paths: {
            type: "array",
            items: { type: "string" },
            description: "Local files or folders to ingest."
          },
          tags: {
            type: "array",
            items: { type: "string" },
            description: "Optional tags to attach to ingested documents."
          },
          profile: {
            type: "string",
            description: "Optional private-model profile override."
          }
        },
        required: ["paths"]
      },
      async ({ paths = [], tags = [], profile } = {}) =>
        runBridge(
          "ingest",
          [
            ...withProfileArgs(profile, config),
            ...paths,
            ...(tags.length ? ["--tags", ...tags] : []),
            "--max-files",
            String(config.maxIngestFiles)
          ],
          config
        )
    ),
    toolSpec(
      "enclave.chat",
      "Ask a question against the local encrypted context store.",
      {
        type: "object",
        properties: {
          question: {
            type: "string",
            description: "User question about local files and notes."
          },
          profile: {
            type: "string",
            description: "Optional private-model profile override."
          }
        },
        required: ["question"]
      },
      async ({ question, profile }) =>
        runBridge("chat", [...withProfileArgs(profile, config), question], config)
    ),
    toolSpec(
      "enclave.scan",
      "Run local risk scanning with the Sheriff privacy broker.",
      {
        type: "object",
        properties: {
          paths: {
            type: "array",
            items: { type: "string" },
            description: "Paths to scan. Defaults to the user's Documents folder."
          },
          maxFiles: {
            type: "integer",
            description: "Maximum number of files to scan."
          }
        }
      },
      async ({ paths = [], maxFiles }) =>
        runBridge(
          "scan",
          [
            ...(paths.length ? ["--paths", ...paths] : []),
            "--max-files",
            String(Number.isFinite(maxFiles) ? maxFiles : config.maxIngestFiles)
          ],
          config
        )
    ),
    toolSpec(
      "enclave.protect",
      "Enable consent barriers for selected local paths.",
      {
        type: "object",
        properties: {
          paths: {
            type: "array",
            items: { type: "string" },
            description: "Paths to protect."
          }
        },
        required: ["paths"]
      },
      async ({ paths }) => runBridge("protect", [...paths], config)
    ),
    toolSpec(
      "enclave.read",
      "Read a protected file through a valid Sheriff lease.",
      {
        type: "object",
        properties: {
          resource: {
            type: "string",
            description: "Absolute file path."
          },
          leaseId: {
            type: "string",
            description: "Lease token issued by enclave.scan/request_access."
          },
          redact: {
            type: "boolean",
            default: true,
            description: "Whether to redact sensitive tokens."
          }
        },
        required: ["resource", "leaseId"]
      },
      async ({ resource, leaseId, redact = true }) =>
        runBridge("read", [resource, leaseId, redact ? "--redact" : "--no-redact"], config)
    ),
    toolSpec(
      "enclave.adapters",
      "Inspect local WDVA adapters and the recommended model profile.",
      {
        type: "object",
        properties: {
          profile: {
            type: "string",
            description: "Optional private-model profile override."
          }
        }
      },
      async ({ profile } = {}) =>
        runBridge("adapters", withProfileArgs(profile, config), config)
    )
  ];

  for (const spec of tools) {
    registerTool(api, spec);
  }

  return {
    manifest: enclavePluginManifest,
    config,
    tools: tools.map(({ name, description, inputSchema }) => ({ name, description, inputSchema }))
  };
}

export default {
  manifest: enclavePluginManifest,
  registerWithApi
};
