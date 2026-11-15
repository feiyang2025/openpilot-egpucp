#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_err_fun(double *nom_x, double *delta_x, double *out_5621847562774482709);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_6433411341470746887);
void car_H_mod_fun(double *state, double *out_1549433459195114425);
void car_f_fun(double *state, double dt, double *out_6294660566595538893);
void car_F_fun(double *state, double dt, double *out_1214373718580184770);
void car_h_25(double *state, double *unused, double *out_1850377977919926149);
void car_H_25(double *state, double *unused, double *out_3354258365989550415);
void car_h_24(double *state, double *unused, double *out_8505439987153360673);
void car_H_24(double *state, double *unused, double *out_5531472789596700388);
void car_h_30(double *state, double *unused, double *out_9037330882377984478);
void car_H_30(double *state, double *unused, double *out_1173437964138057783);
void car_h_26(double *state, double *unused, double *out_4407739923670721493);
void car_H_26(double *state, double *unused, double *out_387244952884505809);
void car_h_27(double *state, double *unused, double *out_4454783298728623800);
void car_H_27(double *state, double *unused, double *out_3348201275938482694);
void car_h_29(double *state, double *unused, double *out_4611969967079752945);
void car_H_29(double *state, double *unused, double *out_663206619823665599);
void car_h_28(double *state, double *unused, double *out_2606689624252818460);
void car_H_28(double *state, double *unused, double *out_1300423651741660652);
void car_h_31(double *state, double *unused, double *out_8005825173760586278);
void car_H_31(double *state, double *unused, double *out_1013453055117857285);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_mass(double x);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}