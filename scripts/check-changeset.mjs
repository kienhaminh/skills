import { execFileSync } from "node:child_process";

const baseRef = process.argv[2] ?? process.env.GITHUB_BASE_REF ?? "main";
const remoteBaseRef = baseRef.startsWith("origin/") ? baseRef : `origin/${baseRef}`;

function changedFiles(ref) {
  return execFileSync("git", ["diff", "--name-only", `${ref}...HEAD`], {
    encoding: "utf8",
  })
    .split("\n")
    .filter(Boolean);
}

let files;
try {
  files = changedFiles(remoteBaseRef);
} catch {
  try {
    files = changedFiles(baseRef);
  } catch {
    console.error(
      `Cannot compare against ${baseRef}. Fetch the base branch or pass it explicitly: npm run check:changeset -- <base-ref>`,
    );
    process.exit(2);
  }
}

const changesSkill = files.some(
  (file) => file.startsWith("skills/") && file !== "skills/.gitkeep",
);
const hasChangeset = files.some(
  (file) => /^\.changeset\/[^/]+\.md$/.test(file),
);

if (changesSkill && !hasChangeset) {
  console.error(
    "A skill changed without a Changeset. Run `npm run changeset` and commit the generated .changeset/*.md file.",
  );
  process.exit(1);
}

console.log(
  changesSkill
    ? "Skill change has a Changeset."
    : "No installable skill changed; no Changeset is required.",
);
