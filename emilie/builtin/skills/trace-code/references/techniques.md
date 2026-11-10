# Tracing techniques

Reach for this when plain search stops giving answers.

## 1. Choosing and widening the anchor

- **Search the user-visible string**, not the concept. UI labels, error messages, log lines and CLI help text are unique and
  usually sit next to the code that matters. If it is translated, search the translation file's key, then the key.
- **Try the naming variants.** `price_order`, `priceOrder`, `PriceOrder`, `price-order`, `PRICE_ORDER`. Frameworks convert
  between them (routes `price-order`, handler `priceOrder`, table `price_orders`).
- **Search both ends.** Where the value is produced and where it is consumed. Meeting in the middle is faster than a long
  walk from one end.
- **Use the type or schema.** A request DTO, a protobuf message, a GraphQL type, a JSON schema or a database model has a
  name that appears at every hop. Follow the *type*.
- **Count the hits.** 3 hits: read them all. 30 hits: group by file and read the central file first. 300 hits: your anchor
  is too generic; narrow it with the path or a longer string.

## 2. Resolving calls that have no visible definition

| Pattern | How to recognize | Where the real link is |
|---|---|---|
| Route decorator / annotation | `@app.get("/x")`, `@GetMapping`, `[HttpPost]`, `@Controller` | the decorated function *is* the handler; the path string is the anchor |
| Route table | `urls.py`, `routes.rb`, `router.get('/x', handler)`, `routes.ts` | the table maps a path to a handler by name |
| Registry / dispatch dict | `HANDLERS[name] = fn`, `register("x", cls)`, `plugins = {...}` | find the `register` calls and the lookup `HANDLERS[key]` |
| Dependency injection | `@Inject`, constructor parameters, `container.bind(IFoo).to(Foo)`, FastAPI `Depends(...)` | the binding or module file picks the implementation |
| Interface / abstract base | `interface Foo`, `class Foo(ABC)`, `trait Foo` | list implementations: search `implements Foo`, `extends Foo`, `(Foo)`, `impl Foo for` |
| Event bus / pub-sub | `emit("order.created")`, `bus.publish`, `on("x", fn)`, `@Subscribe`, signals (`post_save`) | search the **event name string** in both emit and subscribe sites |
| Middleware / interceptors | `app.use(...)`, `MIDDLEWARE = [...]`, filters, `@UseGuards`, `before_action` | the ordered list defines what runs before and after the handler |
| ORM / query builders | `Model.objects.filter`, `repo.findBy`, `@Entity`, Prisma/SQLAlchemy models | the model definition is the schema; look for hooks (`save()`, triggers, `@PrePersist`) |
| Config-driven pipelines | YAML/JSON naming classes, steps or jobs | the loader that turns names into objects (`importlib`, `Class.forName`, `require(name)`) |
| Reflection / metaprogramming | `getattr`, `__getattr__`, `method_missing`, `eval`, `Reflect`, proxies | the string being passed in; trace the *value*, not the call |
| Callbacks / higher-order | function passed as an argument, `.map(fn)`, `setTimeout(fn)` | find where the argument is created and where it is finally invoked |
| Code generation | `*_pb2.py`, `*.generated.*`, `schema.graphql`, OpenAPI clients | the *source* spec (`.proto`, `.graphql`, OpenAPI file) and the generator config |
| Macros / build-time | Rust `macro_rules!`, C preprocessor, Babel/webpack plugins | the macro or plugin definition, and the build step that applies it |
| Frontend state | Redux actions/reducers, Vuex/Pinia, signals, `useEffect` | search the **action type** or store key across dispatch and handler sites |

## 3. Crossing process and service boundaries

A trace often continues in another place. Name the boundary, then find the other side:

- **HTTP call:** the client's URL and method -> the other service's route table (same repo? search the path string).
- **Queue / topic:** producer's topic name -> consumer subscription. Search the topic string.
- **Database:** the SQL or model -> the table definition and migrations -> triggers, views, stored procedures.
- **Cron / scheduler:** `crontab`, `@Scheduled`, `schedule:`, CI schedules, Kubernetes CronJob.
- **Shell-outs:** `subprocess`, `exec`, backticks, `Process.Start` -> the script or binary being called.
- **Browser <-> server:** `fetch('/api/x')` -> the server route. Check the proxy config if the path does not match.

If the other side is in a different repository, stop at the boundary, record the contract (URL, payload, topic), and say
what to read there.

## 4. Tracing a value backward ("where does this come from?")

1. Find where the value is *used* (the line the user points at).
2. Find the assignment that reaches it: parameter? local? field? global? config? Walk up to the nearest definition.
3. If it is a parameter, find the callers (the finder's CALLS group) and look at the argument they pass.
4. Repeat until you reach a source: user input, a database read, a config or environment variable, a constant, or a clock.
5. Note every transformation on the way (parse, default, clamp, rename); bugs hide there.

## 5. Tracing from a stack trace

- Read it from the **bottom up** for Python (oldest call first) and from the **top down** for Java and JavaScript
  (the throw site first), and check which convention this one uses.
- The deepest frame in *your* code (not the library) is the throw site; the frames above it are how you got there.
- Open each of your own frames at the given line, and read the 10 lines above it for the branch that led there.

## 6. Git archaeology (read-only)

```
git log -S"exact text" --oneline -- <path>        # commits that added or removed this text
git log -G"regex" --oneline -- <path>             # commits whose diff matches a pattern
git log -L :<function>:<file>                     # the history of one function
git blame -L <a>,<b> <file>                       # who last touched these lines, and in which commit
git show <commit> --stat                          # what else changed with it (the reason is often in the neighbours)
```
A commit message that says *why* is worth quoting. Use history to explain "why is it like this", not to guess behaviour.

## 7. Reading async and concurrent code

- `await`, `.then`, promises, goroutines, threads and queues mean **order is not source order**. Draw the sequence from the
  *awaited* calls, and note what runs concurrently.
- Find the *join* point (where results are awaited together) and the *error* path (what happens to a rejected promise,
  a failed task, a dead worker).
- Shared mutable state between tasks is the usual source of surprising behaviour: list it.

## 8. Minified, bundled or compiled code

- Prefer the **source map** (`*.map`) or the original source in the repository.
- Search for string literals and property names (they survive minification); function names often do not.
- If only the bundle exists, say so and lower your confidence: a trace through minified code is a *hypothesis*.

## 9. When you get stuck

- Say what you searched and what you found. A short list of leads beats a confident guess.
- Ask the user for one fact that would unblock you (the URL they call, the error text, the config in use).
- Offer a runtime check: a breakpoint at the entry, or one log line, run by the user.
