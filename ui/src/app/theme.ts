import { faCircleHalfStroke, faMoon, faSun, faTerminal } from "@fortawesome/free-solid-svg-icons";
import { Theme } from "./interfaces/theme";


export const Themes: Theme[] = [
  {
    id: 'light',
    displayName: 'Light',
    icon: faSun,
  },
  {
    id: 'dark',
    displayName: 'Dark',
    icon: faMoon,
  },
  {
    id: 'auto',
    displayName: 'Auto',
    icon: faCircleHalfStroke,
  },
  // Dark, styled like a command-line tool (_mh-terminal.sass).
  {
    id: 'terminal',
    displayName: 'Terminal',
    icon: faTerminal,
  },
];
