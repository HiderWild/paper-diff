// paper-diff — LaTeX paper version diff + accept merge + Docker compile.
// Copyright (C) paper-diff contributors.
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published
// by the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful, but
// WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the LICENSE
// file in the repository root for the full text (AGPL-3.0-or-later).

import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import i18n from "./i18n";
import "./styles.css";

createApp(App).use(createPinia()).use(i18n).mount("#app");
