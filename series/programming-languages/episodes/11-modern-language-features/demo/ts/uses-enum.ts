// Wrong on purpose: `enum` is not erasable syntax, so Node's type stripping refuses it.
enum Route {
  TeamLead,
  Finance,
  Board,
}
console.log(Route.Finance);
