from pythonforandroid.recipe import CythonRecipe
from pythonforandroid.logger import logger

class AnnoyRecipe(CythonRecipe):
    """ Workaround clang-14 chocking on -march=native when targeting ARM """

    version = '1.17.3'
    url = 'https://github.com/spotify/annoy/archive/refs/tags/v{version}.zip'
    name = 'annoy'
    depends = ['python3', 'setuptools']

    def build_arch(self, arch):
        logger.info('Calling build_arch')
        super(AnnoyRecipe, self).build_arch(arch)

    def get_recipe_env(self, arch=None, with_flags_in_cc=True):
        env = super(AnnoyRecipe, self).get_recipe_env(arch, with_flags_in_cc)

        original_cc = env.get('CC', '')

        # Prepend a command to filter out '-march=native' before calling the original CC
        env['CC'] = (
            "bash -c 'args=(); "
            "for arg in \"$@\"; do "
            "if [ \"$arg\" != \"-march=native\" ]; then "
            "args+=(\"$arg\"); "
            "fi; "
            "done; "
            f"{original_cc} \"${{args[@]}}\"' bash"
        )
        # Log the new CC for debugging purposes
        logger.info(f'Wrapped CC: {env["CC"]}')

        return env

# This is used by P4A to find and instantiate the recipe
recipe = AnnoyRecipe()
