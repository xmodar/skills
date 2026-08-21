// House svgo config: precision 2, structure preserved.
//
// cleanupIds is off because this workflow deliberately creates ids for <use>
// dedup and gradient href inheritance; letting svgo renumber or inline them
// undoes the structural pass. collapseGroups is off for the same reason --
// symmetry groups exist to be referenced, not flattened.
export default {
  multipass: true,
  plugins: [
    {
      name: 'preset-default',
      params: {
        overrides: {
          cleanupIds: false,
          collapseGroups: false,
          moveGroupAttrsToElems: false,
          convertPathData: { floatPrecision: 2, transformPrecision: 3 },
          cleanupNumericValues: { floatPrecision: 2 },
        },
      },
    },
  ],
};
