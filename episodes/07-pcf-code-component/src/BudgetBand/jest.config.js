/** @type {import('jest').Config} */
module.exports = {
    preset: "ts-jest",
    testEnvironment: "node",
    roots: ["<rootDir>/BudgetBand"],
    transform: { "^.+\\.ts$": ["ts-jest", { tsconfig: { strict: true, esModuleInterop: true, types: ["jest"] } }] },
};
