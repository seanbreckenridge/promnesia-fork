/* @flow */
import type {Src} from './common';

// $FlowFixMe
import OptionsSync from 'webext-options-sync';

type SrcMap = {
    [Src]: Src
};

export type Options = {
    host: string;
    token: string;

    dots: boolean;
    blacklist: string;
    src_map: SrcMap;

    position_css: string;
    extra_css: string;

}

// TODO allow to export settings
// https://github.com/fregante/webext-options-sync/issues/23
function defaultOptions(): Options {
    return {
        host: 'http://localhost:13131',
        token: '',

        dots: true,
        blacklist: '',
        src_map: {},


        /* Change these if you want to reposition the sidebar
         * E.g. to display on bottom, use :root { --bottom 1; --size: 25%; }
         * TODO shit, somehow this was breaking on Android... I guess keep it aside
         */

        // TODO FIXME do something if value is invalid?..
        // TODO make it literate from test?
        // TODO hmm. not sure if I can get rid of :root thing without relying on JS?
        position_css: `
.promnesia {
    --right: 1;
    --size: 30%;

    background-color: rgba(236, 236, 236, 0.4);
}
`.trim(),
        // TODO not sure why that in background was necessary..  none repeat scroll 0% 0%;

        // TODO add some docs on configuring it...
        extra_css   : `
.src {
    font-weight: bold;
}
`.trim(),
    };
}


// TODO mm. don't really like having global object, but seems that it's easiest way to avoid race conditions
// see https://github.com/fregante/webext-options-sync/issues/38
const _options = new OptionsSync({
    defaults: defaultOptions(),
});


function optSync() {
    return _options;
}

// TODO later rename to just get_options
export async function get_options_async(): Promise<Options> {
    return await optSync().getAll();
}


/*
function sleeper(ms) {
    return function(x) {
        return new Promise(resolve => setTimeout(() => resolve(x), ms));
    };
}
*/

export async function setOptions(opts: Options) {
    const os = optSync();
    await os.set(opts);
}
