import { parse, unit } from "mathjs";
import type { FunctionNode, OperatorNode, SymbolNode } from "mathjs";

const ALLOWED_FUNCTIONS = new Set([
  "abs",
  "acos",
  "asin",
  "atan",
  "cbrt",
  "ceil",
  "cos",
  "exp",
  "floor",
  "log",
  "log10",
  "max",
  "min",
  "round",
  "sin",
  "sqrt",
  "tan",
]);
const ALLOWED_SYMBOLS = new Set(["e", "pi", ...ALLOWED_FUNCTIONS]);
const ALLOWED_OPERATORS = new Set(["+", "-", "*", "/", "%", "^"]);

/**
 * Evaluates a restricted scalar mathematical expression.
 *
 * @param expression Arithmetic expression without variables or assignments.
 * @returns A finite JavaScript number.
 */
export function calculateExpression(expression: string): number {
  const source = expression.trim();
  if (!source || source.length > 300) {
    throw new Error("Expression must contain between 1 and 300 characters");
  }

  const root = parse(source);
  let nodeCount = 0;
  root.traverse((node) => {
    nodeCount += 1;
    if (nodeCount > 100) {
      throw new Error("Expression is too complex");
    }
    if (
      !["ConstantNode", "OperatorNode", "FunctionNode", "SymbolNode", "ParenthesisNode"].includes(
        node.type,
      )
    ) {
      throw new Error(`${node.type} is not allowed`);
    }
    if (
      node.type === "OperatorNode" &&
      !ALLOWED_OPERATORS.has((node as OperatorNode).op)
    ) {
      throw new Error(`Operator ${(node as OperatorNode).op} is not allowed`);
    }
    if (
      node.type === "FunctionNode" &&
      !ALLOWED_FUNCTIONS.has(
        ((node as FunctionNode).fn as SymbolNode).name ?? "",
      )
    ) {
      throw new Error("Function is not allowed");
    }
    if (
      node.type === "SymbolNode" &&
      !ALLOWED_SYMBOLS.has((node as SymbolNode).name)
    ) {
      throw new Error(`Symbol ${(node as SymbolNode).name} is not allowed`);
    }
  });

  const result: unknown = root.evaluate();
  if (typeof result !== "number" || !Number.isFinite(result)) {
    throw new Error("Expression must produce a finite scalar number");
  }
  return result;
}

/**
 * Converts a numeric value between compatible mathjs units.
 *
 * @param value Numeric value to convert.
 * @param from Source unit name or symbol.
 * @param to Target unit name or symbol.
 * @returns Normalized conversion result.
 */
export function convertUnits(value: number, from: string, to: string) {
  if (!Number.isFinite(value)) {
    throw new Error("Value must be a finite number");
  }
  const sourceUnit = from.trim();
  const targetUnit = to.trim();
  const validUnit = /^[\p{L}\p{N}\s°µμ/*^()._-]{1,50}$/u;
  if (!validUnit.test(sourceUnit) || !validUnit.test(targetUnit)) {
    throw new Error("Unit names contain unsupported characters");
  }

  return {
    value,
    from: sourceUnit,
    to: targetUnit,
    convertedValue: unit(value, sourceUnit).toNumber(targetUnit),
  };
}
