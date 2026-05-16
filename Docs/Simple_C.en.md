# Simple C

Simple C is the small C compiler used by Simple OS experiments.

This English document is a companion summary. The primary document is the
Japanese version:

```text
Docs/Simple_C.md
```

## Purpose

Simple C is not an ISO C implementation. It is a practical Unix V6 C style subset
compiler for this repository's educational OS and custom ISA.

It is used to:

- compile small user programs for Simple OS
- make it possible to write Simple OS itself incrementally in C
- keep OS logic readable while preserving low-level assembly boundaries

## Implementation

Simple C is intentionally direct:

- `ccpre.py`: minimal preprocessor
- `cclex.py`: hand-written lexer
- `ccparse.py`: hand-written recursive descent parser
- `ccgen.py`: direct assembly generator
- `cc.py`: compiler driver
- `cclib/runtime.asm`: user-program runtime

It does not currently use yacc, bison, ANTLR, or another parser generator.
It also does not currently have a separate IR or optimizer.

## Background References

Useful compiler and C background:

- Brian W. Kernighan and Dennis M. Ritchie, *The C Programming Language*
- Alfred V. Aho, Monica S. Lam, Ravi Sethi, Jeffrey D. Ullman,
  *Compilers: Principles, Techniques, and Tools*
- Andrew W. Appel, *Modern Compiler Implementation*
- Christopher W. Fraser and David R. Hanson, *A Retargetable C Compiler*
- Jack Crenshaw, *Let's Build a Compiler*
- Nora Sandler, *Writing a C Compiler*
- Abdulaziz Ghuloum, *An Incremental Approach to Compiler Construction*

These are listed as study background. This repository does not copy textbook
text, diagrams, or substantial code examples from those sources.

## Supported Subset

Simple C currently supports:

- `int`, `char`, pointers, arrays, and `struct`
- functions with stack arguments and `R0` return values
- `if`, `while`, `for`, `break`, `continue`, `return`
- arithmetic, comparison, logical, bitwise, and shift operators
- `sizeof`
- string literals and character literals
- global variables and limited global initializers
- inline `asm("...");`
- top-level `asm(".ADDR ...");` for OS fixed-address placement

OS-facing features include `--no-runtime`, top-level `asm(".ADDR ...")`,
fixed-address wrappers, `sizeof`, global initializers, bitwise operators, shifts,
pointer arithmetic, and packed structs. In this repository, the work to rewrite
Simple OS incrementally in C is called Phase 8.

## ABI

- arguments are pushed on the stack from right to left
- return value is in `R0`
- `R7` is the frame pointer
- caller-saved: `R0` to `R3`, `R8`, `R9`
- callee-saved by convention: `R4` to `R7`

## Limitations

Current limitations include:

- no optimizer
- no register allocator
- no separate IR
- no function pointers
- no casts
- no `typedef`, `enum`, or `union`
- no variadic functions
- no local array or struct initializers
- no struct value passing or return

## License

Simple C source code is licensed under the repository root MIT License unless a
file says otherwise.

Documentation is licensed as described in `Docs/LICENSE.md`.
