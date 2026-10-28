// Tests of get-token.sh against a fake Cognito on localhost. Run them with: node --test scripts/get-token.test.mjs
// Nothing here reaches the real Cognito: the script only accepts an alternative endpoint on localhost or 127.0.0.1.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chmodSync, existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { after, afterEach, before, describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), "get-token.sh");
const EMAIL = "jane.doe+e2e@geoq.es";
const CLIENT_ID = "1a2b3c4d5e6f7g8h9i0j";
const ID_TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.fake-signature-1118";
const SECRET_MARKER = "BODY-OF-THE-RESPONSE-MUST-NEVER-BE-PRINTED";
const HARD_PASSWORD = `a"b'c\\d,e$f%g h=i \`x\` $(echo pwned)\\`;
const PASSWORDS = [HARD_PASSWORD, '"', "'", "\\", ",", "$", "%", " spaced ", "=", "p@ss=w0rd==", "end-with-backslash\\"];

let server;
let endpoint;
let workDir;
let received = [];
let answer;

before(async () => {
  server = createServer((request, response) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      received.push({ method: request.method, headers: request.headers, body: Buffer.concat(chunks).toString("utf8") });
      const { status, body } = answer();
      response.writeHead(status, { "Content-Type": "application/x-amz-json-1.1" });
      response.end(JSON.stringify(body));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  endpoint = `http://127.0.0.1:${server.address().port}/`;
  workDir = mkdtempSync(join(tmpdir(), "get-token-test-"));
});

after(() => {
  server.close();
  rmSync(workDir, { recursive: true, force: true });
});

afterEach(() => {
  received = [];
});

const success = () => ({ status: 200, body: { AuthenticationResult: { IdToken: ID_TOKEN, ExpiresIn: 3600 } } });
const failure = (type, message = SECRET_MARKER) => () => ({ status: 400, body: { __type: type, message } });

/** Runs the script with a throwaway .env and token path; the password comes from E2E_PASSWORD, as the tests are allowed to. */
function run({ env = `SEED_USER_EMAIL=${EMAIL}\nCOGNITO_CLIENT_ID=${CLIENT_ID}\n`, password = HARD_PASSWORD, endpointUrl = endpoint, extraPath } = {}) {
  const dir = mkdtempSync(join(workDir, "case-"));
  const envFile = join(dir, ".env");
  const tokenFile = join(dir, ".auth", "token.json");
  writeFileSync(envFile, env);
  return new Promise((resolve) => {
    // No stdin and a time limit: a script that waits for a typed password must fail here, never hang.
    const child = spawn("bash", [SCRIPT], {
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 20_000,
      env: {
        PATH: `${extraPath ? `${extraPath}:` : ""}${process.env.PATH}`,
        HOME: process.env.HOME,
        E2E_ENV_FILE: envFile,
        E2E_TOKEN_FILE: tokenFile,
        E2E_COGNITO_ENDPOINT: endpointUrl,
        E2E_PASSWORD: password,
      },
    });
    let output = "";
    child.stdout.on("data", (chunk) => (output += chunk));
    child.stderr.on("data", (chunk) => (output += chunk));
    child.on("close", (code) => resolve({ code, output, tokenFile }));
  });
}

describe("the request sent to Cognito", () => {
  for (const password of PASSWORDS) {
    it(`is valid JSON with exactly the email, the client and the password ${JSON.stringify(password)}`, async () => {
      answer = success;

      const result = await run({ password });

      assert.equal(result.code, 0, result.output);
      assert.equal(received.length, 1);
      const [request] = received;
      assert.equal(request.method, "POST");
      assert.equal(request.headers["x-amz-target"], "AWSCognitoIdentityProviderService.InitiateAuth");
      assert.equal(request.headers["content-type"], "application/x-amz-json-1.1");
      assert.deepEqual(JSON.parse(request.body), {
        AuthFlow: "USER_PASSWORD_AUTH",
        ClientId: CLIENT_ID,
        AuthParameters: { USERNAME: EMAIL, PASSWORD: password },
      });
    });
  }

  const dirtyEnvs = {
    "double quotes": `SEED_USER_EMAIL="${EMAIL}"\nCOGNITO_CLIENT_ID="${CLIENT_ID}"\n`,
    "single quotes": `SEED_USER_EMAIL='${EMAIL}'\nCOGNITO_CLIENT_ID='${CLIENT_ID}'\n`,
    "spaces around the values": `SEED_USER_EMAIL=  ${EMAIL}  \nCOGNITO_CLIENT_ID=  ${CLIENT_ID}  \n`,
    "spaces inside quotes": `SEED_USER_EMAIL=" ${EMAIL} "\nCOGNITO_CLIENT_ID=" ${CLIENT_ID} "\n`,
    "a trailing carriage return": `SEED_USER_EMAIL=${EMAIL}\r\nCOGNITO_CLIENT_ID=${CLIENT_ID}\r\n`,
    "quotes, spaces and a carriage return together": `OTHER=1\r\nSEED_USER_EMAIL="  ${EMAIL} "\r\nCOGNITO_CLIENT_ID='${CLIENT_ID}'  \r\n`,
  };
  for (const [name, env] of Object.entries(dirtyEnvs)) {
    it(`takes the clean email and client from a .env with ${name}`, async () => {
      answer = success;

      const result = await run({ env });

      assert.equal(result.code, 0, result.output);
      const sent = JSON.parse(received[0].body);
      assert.equal(sent.AuthParameters.USERNAME, EMAIL);
      assert.equal(sent.ClientId, CLIENT_ID);
    });
  }
});

describe("the token", () => {
  it("is written to the token file, which is private, and never printed", async () => {
    answer = success;

    const result = await run();

    assert.deepEqual(JSON.parse(readFileSync(result.tokenFile, "utf8")), { id_token: ID_TOKEN });
    assert.equal(statModeOf(result.tokenFile), 0o600);
    assert.ok(!result.output.includes(ID_TOKEN));
    assert.ok(!result.output.includes(HARD_PASSWORD));
  });

  it("does not use the aws binary", async () => {
    answer = success;
    const binDir = mkdtempSync(join(workDir, "bin-"));
    const marker = join(binDir, "aws-was-called");
    writeFileSync(join(binDir, "aws"), `#!/bin/sh\ntouch "${marker}"\nexit 1\n`);
    chmodSync(join(binDir, "aws"), 0o755);

    const result = await run({ extraPath: binDir });

    assert.equal(result.code, 0, result.output);
    assert.ok(!existsSync(marker));
  });
});

const statModeOf = (path) => statSync(path).mode & 0o777;

describe("the errors", () => {
  const cases = {
    credentials: { reply: failure("NotAuthorizedException"), message: /wrong password or unknown user/, code: 3 },
    "an unknown user": { reply: failure("UserNotFoundException"), message: /wrong password or unknown user/, code: 3 },
    "a flow that is not enabled": {
      reply: failure("InvalidParameterException", `USER_PASSWORD_AUTH flow not enabled for this client ${SECRET_MARKER}`),
      message: /does not allow USER_PASSWORD_AUTH/,
      code: 4,
    },
    "invalid parameters": { reply: failure("InvalidParameterException", `1 validation error ${SECRET_MARKER}`), message: /script or configuration fault/, code: 2 },
    "an unknown client": { reply: failure("ResourceNotFoundException"), message: /script or configuration fault/, code: 2 },
    "a new-password challenge": {
      reply: () => ({ status: 200, body: { ChallengeName: "NEW_PASSWORD_REQUIRED", Session: SECRET_MARKER } }),
      message: /requires a new password/,
      code: 5,
    },
    "another challenge": {
      reply: () => ({ status: 200, body: { ChallengeName: "SMS_MFA", Session: SECRET_MARKER } }),
      message: /extra step/,
      code: 5,
    },
    "an unknown error": { reply: failure("SomethingNewException"), message: /does not recognise/, code: 9 },
    "an answer without a token": { reply: () => ({ status: 200, body: { AuthenticationResult: {}, note: SECRET_MARKER } }), message: /without an ID token/, code: 9 },
  };
  const seen = new Map();

  for (const [name, { reply, message, code }] of Object.entries(cases)) {
    it(`gives its own message for ${name}, never the response or the password, and writes no token`, async () => {
      answer = reply;

      const result = await run();

      assert.equal(result.code, code, result.output);
      assert.match(result.output, message);
      assert.ok(!result.output.includes(HARD_PASSWORD), "the password is printed");
      assert.ok(!result.output.includes(SECRET_MARKER), "the response is printed");
      assert.ok(!result.output.includes(CLIENT_ID), "the client id is printed");
      assert.ok(!result.output.includes(EMAIL), "the email is printed");
      assert.ok(!existsSync(result.tokenFile));
      seen.set(name, result.output.trim());
    });
  }

  it("tells the credentials, the flow and the challenge apart", () => {
    const distinct = ["credentials", "a flow that is not enabled", "invalid parameters", "a new-password challenge"].map((name) => seen.get(name));
    assert.equal(new Set(distinct).size, distinct.length);
  });
});

describe("the endpoint", () => {
  for (const url of ["https://cognito-idp.example.com/", "http://localhost.evil.example/", "http://127.0.0.1@evil.example/", "http://10.0.0.1:9/"]) {
    it(`is refused for ${url}`, async () => {
      answer = success;

      const result = await run({ endpointUrl: url });

      assert.equal(result.code, 8, result.output);
      assert.match(result.output, /only accepted for localhost or 127\.0\.0\.1/);
      assert.equal(received.length, 0);
    });
  }
});

describe("the configuration", () => {
  it("says what is missing from .env without printing anything else", async () => {
    answer = success;

    const result = await run({ env: `SEED_USER_EMAIL=${EMAIL}\n` });

    assert.equal(result.code, 2);
    assert.match(result.output, /COGNITO_CLIENT_ID/);
    assert.equal(received.length, 0);
  });
});
